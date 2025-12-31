import asyncio
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

import docx
import httpx
import pandas as pd
import PyPDF2
import pytesseract
from pdf2image import convert_from_path
from PIL import Image
from sqlalchemy.orm import joinedload

from app.db.models import (
    ConversionJob,
    ImportTemplate,
    LinkedOrganization,
    MappingProfile,
)
from app.db.session import SessionLocal
from app.infrastructure.celery_app import celery
from app.infrastructure.erpnext_client import ERPNextClient

UPLOAD_DIR = Path("/app/uploads")
PROCESSED_DIR = UPLOAD_DIR / "processed"


def read_tabular_file(file_path: Path, header_row: int = 0) -> pd.DataFrame:
    """Reads any tabular file (Excel, CSV) into a pandas DataFrame, using the specified header row."""
    ext = file_path.suffix.lower()
    if ext in [".xlsx", ".xls"]:
        return pd.read_excel(file_path, header=header_row)
    elif ext == ".csv":
        try:
            return pd.read_csv(
                file_path, encoding="utf-8", on_bad_lines="skip", header=header_row
            )
        except UnicodeDecodeError:
            return pd.read_csv(
                file_path, encoding="latin-1", on_bad_lines="skip", header=header_row
            )
    raise ValueError(f"Unsupported tabular file format for direct parsing: {ext}")


def ocr_to_dataframe(file_path: Path) -> pd.DataFrame:
    """Converts a PDF or Image file to a text block via OCR, then to a DataFrame."""
    text = ""
    ext = file_path.suffix.lower()
    if ext == ".pdf":
        try:
            pages = convert_from_path(str(file_path))
            for page in pages:
                text += pytesseract.image_to_string(page) + "\n"
        except Exception:
            with open(file_path, "rb") as f:
                reader = PyPDF2.PdfReader(f)
                for page in reader.pages:
                    extracted = page.extract_text()
                    if extracted:
                        text += extracted + "\n"
    elif ext in [".png", ".jpg", ".jpeg", ".tiff", ".bmp"]:
        text = pytesseract.image_to_string(Image.open(file_path))
    elif ext == ".docx":
        doc = docx.Document(file_path)
        text = "\n".join([para.text for para in doc.paragraphs])

    lines = [
        re.split(r"\s{2,}", line.strip()) for line in text.splitlines() if line.strip()
    ]
    if not lines:
        return pd.DataFrame()

    header_candidate = max(lines, key=len)
    header_len = len(header_candidate)

    data = [
        line
        for line in lines
        if len(line) >= header_len - 1 and len(line) <= header_len + 1
    ]

    return pd.DataFrame(data, columns=header_candidate if data else None)


def template_driven_parser(
    df: pd.DataFrame,
    config: Dict[str, Any],
    year: int,
    month: int,
    mapping_rules: Dict[str, str] = None,
) -> List[Dict[str, Any]]:
    """A single, powerful parser that interprets a DataFrame based on a user-defined template config."""
    mode = config.get("mode")
    if not mode:
        raise ValueError("Import template config is missing required 'mode' key.")

    cleaned_columns = {col: str(col).strip() for col in df.columns}
    df = df.rename(columns=cleaned_columns)

    records = []

    try:
        if mode == "DATE_REFERENCE":
            employee_col = config.get("employee_id_column", "").strip()
            dates_col = config.get("dates_column", "").strip()
            status_to_apply = config.get("status_to_apply")

            if not all([employee_col, dates_col, status_to_apply]):
                raise ValueError(
                    "DATE_REFERENCE config is missing one of 'employee_id_column', 'dates_column', or 'status_to_apply'."
                )

            df = df.dropna(subset=[employee_col, dates_col]).astype(str)

            for _, row in df.iterrows():
                emp_code = row[employee_col].strip()
                dates_str = row[dates_col].strip()
                date_numbers = re.findall(r"(\d+)", dates_str)
                for day_str in date_numbers:
                    try:
                        date = f"{year}-{month:02d}-{int(day_str):02d}"
                        datetime.strptime(date, "%Y-%m-%d")
                        records.append(
                            {
                                "employee": emp_code,
                                "attendance_date": date,
                                "status": status_to_apply,
                            }
                        )
                    except (ValueError, TypeError):
                        continue

        elif mode == "MATRIX":
            employee_col = config.get("employee_id_column", "").strip()
            start_col_header = str(config.get("start_column", "")).strip()

            if not all([employee_col, start_col_header, mapping_rules is not None]):
                raise ValueError(
                    "MATRIX config is missing required keys or a mapping profile is not linked."
                )

            df = df.dropna(subset=[employee_col]).astype(str)

            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(-1)
                cleaned_columns = {col: str(col).strip() for col in df.columns}
                df = df.rename(columns=cleaned_columns)

            start_index = df.columns.get_loc(start_col_header)
            day_columns = df.columns[start_index : start_index + 31]

            for _, row in df.iterrows():
                emp_code = row[employee_col].strip()
                for day_header in day_columns:
                    day_match = re.search(r"(\d+)", str(day_header))
                    if not day_match:
                        continue
                    day = int(day_match.group(1))

                    code = row[day_header].strip().upper()
                    target_status = mapping_rules.get(code)

                    if target_status and target_status != "IGNORE":
                        try:
                            date = f"{year}-{month:02d}-{day:02d}"
                            datetime.strptime(date, "%Y-%m-%d")
                            records.append(
                                {
                                    "employee": emp_code,
                                    "attendance_date": date,
                                    "status": target_status,
                                }
                            )
                        except (ValueError, TypeError):
                            continue
        else:
            raise ValueError(f"Unsupported parsing mode: '{mode}'")

    except KeyError as e:
        raise KeyError(
            f"A configured column name was not found in the source file. "
            f"Missing Column: {e}. "
            f"Available columns after cleaning are: {df.columns.tolist()}"
        ) from e

    for record in records:
        record.setdefault("leave_type", "")

    return records


@celery.task
def process_file_task(job_id: int):
    """Main Celery task."""
    db = SessionLocal()
    job = None
    try:
        job = db.query(ConversionJob).filter(ConversionJob.id == job_id).first()
        if not job:
            return f"Job {job_id} not found."

        job.status = "PROCESSING"
        db.commit()

        source_path = UPLOAD_DIR / job.storage_filename
        PROCESSED_DIR.mkdir(exist_ok=True)
        raw_json_path = PROCESSED_DIR / f"{source_path.stem}_raw.json"
        processed_json_path = PROCESSED_DIR / f"{source_path.stem}_processed.json"

        df = pd.DataFrame()
        file_ext = source_path.suffix.lower()

        header_row = 0
        template = None
        mapping_rules = {}

        if job.import_template_id:
            template = (
                db.query(ImportTemplate)
                .filter(ImportTemplate.id == job.import_template_id)
                .first()
            )

        if job.mapping_profile_id:
            profile = (
                db.query(MappingProfile)
                .options(joinedload(MappingProfile.mappings))
                .filter(MappingProfile.id == job.mapping_profile_id)
                .first()
            )
            if profile:
                mapping_rules = {
                    m.source_code.upper(): m.target_status for m in profile.mappings
                }

        if template and template.config:
            header_row = template.config.get("header_row", 0)

        if file_ext in [".xlsx", ".xls", ".csv"]:
            df = read_tabular_file(source_path, header_row=header_row)
        elif file_ext in [".pdf", ".png", ".jpg", ".jpeg", ".docx"]:
            df = ocr_to_dataframe(source_path)
        else:
            raise ValueError(f"Unsupported file type: {file_ext}")

        df.to_json(raw_json_path, orient="records", indent=2)

        extracted_data = []
        if job.target_doctype.lower() == "attendance":
            if not template:
                raise ValueError("Attendance job requires an Import Template.")
            if not job.attendance_year or not job.attendance_month:
                raise ValueError("Attendance job is missing Year or Month.")

            extracted_data = template_driven_parser(
                df=df,
                config=template.config,
                year=job.attendance_year,
                month=job.attendance_month,
                mapping_rules=mapping_rules,
            )
        else:
            extracted_data = df.to_dict(orient="records")

        with open(processed_json_path, "w", encoding="utf-8") as f:
            json.dump(extracted_data, f, indent=2, ensure_ascii=False)

        job.raw_data_path = str(raw_json_path)
        job.processed_data_path = str(processed_json_path)
        job.status = "AWAITING_VALIDATION"
        db.commit()
        return f"Successfully processed {job.original_filename}"

    except Exception as e:
        if job:
            db.rollback()
            job.status = "EXTRACTION_FAILED"
            job.error_log = {"step": "extraction", "message": str(e)}
            db.commit()
        raise
    finally:
        db.close()


@celery.task(bind=True)
def submit_to_erpnext_task(self, job_id: int):
    """Submits the validated data to ERPNext using a dynamic shift type from the template."""
    db = SessionLocal()
    job = None
    try:
        job = (
            db.query(ConversionJob)
            .options(joinedload(ConversionJob.import_template))
            .filter(ConversionJob.id == job_id)
            .first()
        )

        if not job:
            return f"Job {job_id} not found."

        target_org = (
            db.query(LinkedOrganization)
            .filter(LinkedOrganization.id == job.target_org_id)
            .first()
        )
        if not target_org:
            raise ValueError(f"Target organization not found for job {job_id}")

        shift_type = None  # We will not send shift unless specified
        if (
            job.import_template
            and job.import_template.config
            and "shift_type" in job.import_template.config
        ):
            shift_type = job.import_template.config["shift_type"]

        if shift_type:
            print(
                f"--- Using Shift Type: '{shift_type}' for all records in this job ---"
            )
        else:
            print(
                "--- No Shift Type specified in template. 'shift' field will not be sent. ---"
            )

        job.status = "SUBMITTING"
        db.commit()

        with open(job.processed_data_path, "r", encoding="utf-8") as f:
            records = json.load(f)

        if not isinstance(records, list):
            raise TypeError("Data for submission must be a list of records.")

        erp_client = ERPNextClient(
            base_url=target_org.erpnext_url,
            api_key=target_org.api_key,
            api_secret=target_org.api_secret,
        )

        total_records = len(records)
        success_count = 0
        errors = []

        print(f"--- Starting ERPNext Submission for Job ID: {job_id} ---")
        print(f"Found {total_records} records to submit.")

        async def run_submission():
            nonlocal success_count, errors
            for i, record in enumerate(records):
                error_message_for_this_record = None

                print(
                    f"--> Processing record {i + 1}/{total_records}: Employee {record.get('employee')} on {record.get('attendance_date')}"
                )

                try:
                    # --- START OF CHANGE: Build the payload dynamically ---
                    payload = {
                        "employee": record.get("employee"),
                        "attendance_date": record.get("attendance_date"),
                        "status": record.get("status"),
                        "docstatus": 1,
                    }
                    # Only add employee_name if it exists in our record
                    if record.get("employee_name"):
                        payload["employee_name"] = record.get("employee_name")

                    # Only add shift if it was defined in the template
                    if shift_type:
                        payload["shift"] = shift_type

                    # --- ADDED PAYLOAD LOGGING ---
                    print(f"    PAYLOAD: {json.dumps(payload)}")
                    # --- END OF CHANGE ---

                    response = await erp_client.create_document("Attendance", payload)
                    response.raise_for_status()
                    success_count += 1

                except httpx.HTTPStatusError as e:
                    print(f"!!! FAILED record {i + 1}: HTTP {e.response.status_code}")
                    try:
                        error_data = e.response.json()
                        if "_server_messages" in error_data:
                            messages = json.loads(error_data["_server_messages"])
                            error_parts = []
                            for msg in messages:
                                if isinstance(msg, dict):
                                    error_parts.append(str(msg.get("message", msg)))
                                else:
                                    error_parts.append(str(msg))
                            error_message_for_this_record = ". ".join(error_parts)
                        elif "exception" in error_data:
                            error_message_for_this_record = error_data.get("exception")
                        else:
                            error_message_for_this_record = str(error_data)
                    except (json.JSONDecodeError, KeyError):
                        error_message_for_this_record = e.response.text[:500]

                except Exception as e:
                    print(f"!!! FAILED record {i + 1}: General Exception - {e}")
                    error_message_for_this_record = str(e)

                if error_message_for_this_record:
                    errors.append(
                        {
                            "record_index": i,
                            "record_data": record,
                            "error": error_message_for_this_record,
                        }
                    )
                    print(f"    ERROR: {error_message_for_this_record}")

                self.update_state(
                    state="PROGRESS", meta={"current": i + 1, "total": total_records}
                )

        asyncio.run(run_submission())

        if errors:
            job.status = "SUBMISSION_FAILED"
            job.error_log = {
                "step": "submission",
                "summary": f"{len(errors)} of {total_records} records failed.",
                "details": errors,
            }
        else:
            job.status = "COMPLETED"

        job.completed_at = datetime.utcnow()
        db.commit()

        summary_message = f"Submission for job {job.id} finished. Success: {success_count}/{total_records}."
        print(f"--- {summary_message} ---")
        return summary_message

    except Exception as e:
        if job:
            db.rollback()
            job.status = "SUBMISSION_FAILED"
            job.error_log = {"step": "submission_setup", "message": str(e)}
            db.commit()
        raise e
    finally:
        db.close()
