# Iridium-main/app/infrastructure/tasks.py

import asyncio
import json
import re
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

import chardet
import docx
import pandas as pd
import PyPDF2
import pytesseract
from pdf2image import convert_from_path
from PIL import Image

from app.db.models import ConversionJob, LinkedOrganization
from app.db.session import SessionLocal
from app.infrastructure.celery_app import celery
from app.infrastructure.erpnext_client import ERPNextClient

UPLOAD_DIR = Path("/app/uploads")
PROCESSED_DIR = UPLOAD_DIR / "processed"


def parse_attendance_text(
    text: str, year: int = 2025, month: int = 10
) -> List[Dict[str, Any]]:
    """
    Parses OCR text from a Gretis-style Attendance Sheet.
    Includes aggressive cleanup for grid lines and merged characters.
    """
    records = []
    lines = text.splitlines()

    print(f"--- DEBUG: Parsing {len(lines)} lines ---")

    # Regex to find Employee Code (5 digit number starting with 20...)
    row_pattern = re.compile(r"(20\d{3})")

    for line in lines:
        if not line.strip():
            continue

        # --- 1. Aggressive Cleanup ---
        # Replace grid lines and brackets with spaces
        clean_line = re.sub(r"[|\[\]\{\}_!]", " ", line)

        # KEY FIX: Force space between attendance codes if they are stuck together.
        # e.g., "PP" -> "P P", "PL" -> "P L", "PA" -> "P A"
        # We look for P, L, A, H followed immediately by another P, L, A, H
        clean_line = re.sub(
            r"([PLAH])(?=[PLAH])", r"\1 ", clean_line, flags=re.IGNORECASE
        )

        # Also separate P from OCR noise like 'l', 'i', 'e' often read from '|'
        # e.g., "Pi" -> "P ", "Pl" -> "P "
        clean_line = re.sub(r"([P])([lie])", r"\1 ", clean_line)

        # Normalize whitespace
        clean_line = re.sub(r"\s+", " ", clean_line).strip()

        # --- 2. Find Employee Code ---
        match = row_pattern.search(clean_line)
        if not match:
            continue

        emp_code = match.group(1)

        # --- 3. Tokenize ---
        tokens = clean_line.split()

        # --- 4. Locate Attendance Block ---
        # Heuristic: Pop the total count if it exists at the end
        if tokens and tokens[-1].replace(".", "", 1).isdigit():
            try:
                if float(tokens[-1]) > 15:  # Assuming worked days > 15
                    tokens.pop()
            except ValueError:
                pass

        days_in_month = 31

        # Validation: We need at least EmpCode + Name (1) + Days (31) tokens
        if len(tokens) < (days_in_month + 1):
            # Try to salvage: if we have EmpCode, assume the *end* of the string is the attendance
            # and just grab the last N tokens we have, mapping them to the end of the month.
            # But for safety, we'll just skip and log.
            # print(f"Skipping line (tokens={len(tokens)}): {clean_line[:30]}...")
            continue

        # Extract the last 31 tokens as daily statuses
        daily_statuses = tokens[-days_in_month:]

        # --- 5. Extract Name ---
        try:
            code_idx = tokens.index(emp_code)
            # Determine where attendance starts
            att_start_idx = len(tokens) - len(daily_statuses)

            # Name tokens are in between
            name_tokens = tokens[code_idx + 1 : att_start_idx]
            emp_name = " ".join(name_tokens)

            if not emp_name:
                emp_name = "Unknown"
        except (ValueError, IndexError):
            emp_name = "Unknown"

        # --- 6. Process Day Columns ---
        for day_idx, status_code in enumerate(daily_statuses):
            day = day_idx + 1
            status_code = status_code.upper()

            erp_status = None

            # --- MAPPING LOGIC ---
            if status_code in ["P", "p"]:
                continue
            elif status_code == "L":
                erp_status = "On Leave"
            elif status_code == "A":
                erp_status = "Absent"
            # H, P/2, P½ (often OCR'd as P%, P1/2, P?)
            elif any(x in status_code for x in ["H", "/", "½", "%", "1/2"]):
                erp_status = "Half Day"
            # Ignore noise
            elif status_code in ["-", ".", "|", "_", ":", ";", "I", "l", "1"]:
                continue

            if erp_status:
                try:
                    date_str = f"{year}-{month:02d}-{day:02d}"
                    records.append(
                        {
                            "employee": emp_code,
                            "employee_name": emp_name,
                            "attendance_date": date_str,
                            "status": erp_status,
                            "shift": "Standard",
                            "leave_type": "",
                        }
                    )
                except ValueError:
                    continue

    print(f"--- DEBUG: Extracted {len(records)} records ---")
    return records


@celery.task(bind=True)
def submit_to_erpnext_task(self, job_id: int):
    """
    Submits the validated data from a conversion job to ERPNext.
    """
    db = SessionLocal()
    try:
        job = db.query(ConversionJob).filter(ConversionJob.id == job_id).first()
        if not job:
            return f"Job {job_id} not found."

        target_org = (
            db.query(LinkedOrganization)
            .filter(LinkedOrganization.id == job.target_org_id)
            .first()
        )
        if not target_org:
            raise ValueError(
                f"Target organization with ID {job.target_org_id} not found for job {job_id}"
            )

        job.status = "SUBMITTING"
        db.commit()

        if (
            not job.intermediate_data_path
            or not Path(job.intermediate_data_path).exists()
        ):
            raise FileNotFoundError(f"Validated data file not found for job {job_id}")

        with open(job.intermediate_data_path, "r", encoding="utf-8") as f:
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

        async def run_submission():
            nonlocal success_count
            for i, record in enumerate(records):
                try:
                    payload = {
                        "employee": record.get("employee"),
                        "attendance_date": record.get("attendance_date"),
                        "status": record.get("status"),
                        "shift": record.get("shift", "Standard"),
                        "docstatus": 1,
                    }

                    doctype = (
                        "Attendance"
                        if job.target_doctype.lower() == "attendance"
                        else job.target_doctype
                    )

                    response = await erp_client.create_document(doctype, payload)
                    response.raise_for_status()
                    success_count += 1
                except Exception as e:
                    error_message = str(e)
                    if hasattr(e, "response") and e.response:
                        try:
                            error_data = e.response.json()
                            error_message = error_data.get("exception", str(error_data))
                        except json.JSONDecodeError:
                            error_message = e.response.text[:500]

                    errors.append(
                        {
                            "record_index": i,
                            "record_data": record,
                            "error": error_message,
                        }
                    )

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

        return f"Submission for job {job.id} finished. Success: {success_count}/{total_records}."

    except Exception as e:
        job.status = "SUBMISSION_FAILED"
        job.error_log = {"step": "submission_setup", "message": str(e)}
        db.commit()
        raise e
    finally:
        db.close()


@celery.task
def process_file_task(job_id: int):
    """
    The main Celery task for file extraction.
    """
    db = SessionLocal()
    job = db.query(ConversionJob).filter(ConversionJob.id == job_id).first()
    if not job:
        return f"Job {job_id} not found."

    try:
        job.status = "PROCESSING"
        db.commit()

        source_path = UPLOAD_DIR / job.storage_filename
        PROCESSED_DIR.mkdir(exist_ok=True)

        json_path = PROCESSED_DIR / f"{source_path.stem}.json"
        file_ext = source_path.suffix.lower()
        extracted_data = []

        if job.target_doctype.lower() == "attendance":
            text_content = ""
            if file_ext == ".pdf":
                try:
                    pages = convert_from_path(str(source_path))
                    for page in pages:
                        # PSM 6 is optimized for uniform blocks of text (like tables)
                        text_content += pytesseract.image_to_string(
                            page, config="--psm 6"
                        )
                except Exception as e:
                    print(f"PDF OCR Error (pdf2image): {e}")
                    with open(source_path, "rb") as f:
                        reader = PyPDF2.PdfReader(f)
                        for page in reader.pages:
                            text_content += page.extract_text() + "\n"

            elif file_ext in [".png", ".jpg", ".jpeg", ".tiff", ".bmp"]:
                text_content = pytesseract.image_to_string(
                    Image.open(source_path), config="--psm 6"
                )

            # Debug log
            print("--- OCR RAW TEXT START ---")
            print(text_content[:1000])
            print("--- OCR RAW TEXT END ---")

            extracted_data = parse_attendance_text(text_content, year=2025, month=10)

        else:
            if file_ext in [".xlsx", ".xls"]:
                df_no_header = pd.read_excel(source_path, header=None)
                header_row_index = 0
                for i, row in df_no_header.iterrows():
                    if row.notna().sum() > len(row) / 2:
                        header_row_index = i
                        break
                df = pd.read_excel(source_path, header=header_row_index)
                df.columns = [
                    str(c).strip().replace("\n", " ")
                    if pd.notna(c) and "Unnamed" not in str(c)
                    else f"column_{i + 1}"
                    for i, c in enumerate(df.columns)
                ]
                df.dropna(how="all", inplace=True)
                df = df.fillna("").astype(str)
                df.to_json(json_path, orient="records", indent=2, force_ascii=False)
                extracted_data = json.loads(df.to_json(orient="records"))

            elif file_ext == ".csv":
                try:
                    df = pd.read_csv(source_path, encoding="utf-8")
                except UnicodeDecodeError:
                    df = pd.read_csv(source_path, encoding="latin-1")
                df = df.fillna("").astype(str)
                extracted_data = json.loads(df.to_json(orient="records"))

            elif file_ext == ".json":
                with open(source_path, "r") as f:
                    extracted_data = json.load(f)

            else:
                with open(source_path, "rb") as f:
                    raw_data = f.read()
                    enc = chardet.detect(raw_data)["encoding"] or "utf-8"
                    extracted_data = [
                        {"line": l} for l in raw_data.decode(enc).splitlines()
                    ]

        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(extracted_data, f, indent=2, ensure_ascii=False)

        job.intermediate_data_path = str(json_path)
        job.status = "AWAITING_VALIDATION"
        db.commit()

        return f"Successfully processed {job.original_filename} for job {job.id}"

    except Exception as e:
        job.status = "EXTRACTION_FAILED"
        job.error_log = {"step": "extraction", "message": str(e)}
        db.commit()
        raise e
    finally:
        db.close()
