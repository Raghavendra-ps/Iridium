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


def extract_text_from_any_file(file_path: Path) -> str:
    """
    Universal helper to convert any supported file format into a single string of text.
    """
    ext = file_path.suffix.lower()
    text_content = ""

    try:
        # 1. Excel / CSV
        if ext in [".xlsx", ".xls", ".csv"]:
            if ext == ".csv":
                try:
                    df = pd.read_csv(file_path, encoding="utf-8")
                except UnicodeDecodeError:
                    df = pd.read_csv(file_path, encoding="latin-1")
            else:
                df = pd.read_excel(file_path)

            df.dropna(how="all", inplace=True)
            # Convert row to string
            text_list = df.astype(str).apply(lambda x: " ".join(x), axis=1).tolist()
            text_content = "\n".join(text_list)

        # 2. Word
        elif ext == ".docx":
            doc = docx.Document(file_path)
            text_content = "\n".join([para.text for para in doc.paragraphs])
            for table in doc.tables:
                for row in table.rows:
                    row_text = [cell.text for cell in row.cells]
                    text_content += "\n" + " ".join(row_text)

        # 3. PDF
        elif ext == ".pdf":
            try:
                pages = convert_from_path(str(file_path))
                for page in pages:
                    text_content += pytesseract.image_to_string(page, config="--psm 6")
            except Exception as e:
                print(f"PDF Image OCR failed: {e}. Fallback to text extraction.")
                with open(file_path, "rb") as f:
                    reader = PyPDF2.PdfReader(f)
                    for page in reader.pages:
                        text_content += page.extract_text() + "\n"

        # 4. Images
        elif ext in [".png", ".jpg", ".jpeg", ".tiff", ".bmp"]:
            text_content = pytesseract.image_to_string(
                Image.open(file_path), config="--psm 6"
            )

        # 5. JSON
        elif ext == ".json":
            with open(file_path, "r") as f:
                data = json.load(f)
            if isinstance(data, list):
                for item in data:
                    if isinstance(item, dict):
                        text_content += " ".join([str(v) for v in item.values()]) + "\n"
                    else:
                        text_content += str(item) + "\n"

        # 6. Text
        else:
            with open(file_path, "rb") as f:
                raw_data = f.read()
                enc = chardet.detect(raw_data)["encoding"] or "utf-8"
                text_content = raw_data.decode(enc, errors="ignore")

    except Exception as e:
        print(f"Error extracting text from {ext}: {e}")

    return text_content


def parse_attendance_text(
    text: str, year: int = 2025, month: int = 10
) -> List[Dict[str, Any]]:
    """
    Parses OCR text (or converted Excel/Word text) for Attendance.
    Supports formats:
    1. "20535 Name P P P"
    2. "Name EHPL-003 P P P"
    """
    records = []
    lines = text.splitlines()

    print(f"--- DEBUG: Parsing {len(lines)} lines ---")

    # --- IMPROVED REGEX ---
    # Matches:
    # 1. 20xxx (Gretis standard)
    # 2. EHPL-xxx or similar alphanumeric IDs (CSV standard)
    #    Starts with letters, optional hyphen, ends with digits.
    row_pattern = re.compile(r"(\b20\d{3}\b|\b[A-Z]{2,5}[-\s]?\d{2,5}\b)")

    for line in lines:
        if not line.strip():
            continue

        # 1. Cleanup
        clean_line = re.sub(r"[|\[\]\{\}_!]", " ", line)
        # Force space between attendance codes (e.g. PP -> P P)
        clean_line = re.sub(
            r"([PLAH])(?=[PLAH])", r"\1 ", clean_line, flags=re.IGNORECASE
        )
        # Separate P from OCR noise
        clean_line = re.sub(r"([P])([lie])", r"\1 ", clean_line)
        clean_line = re.sub(r"\s+", " ", clean_line).strip()

        # 2. Find Employee Code
        match = row_pattern.search(clean_line)
        if not match:
            continue

        emp_code = match.group(1)

        # 3. Tokenize
        tokens = clean_line.split()

        # 4. Locate Attendance Block
        # Heuristic: Pop 'Total' count if exists
        if tokens and tokens[-1].replace(".", "", 1).isdigit():
            try:
                if float(tokens[-1]) > 15:
                    tokens.pop()
            except ValueError:
                pass

        days_in_month = 31

        if len(tokens) < 5:  # Minimal sanity check
            continue

        # Extract the last 31 tokens as daily statuses
        # We take AT MOST 31. If text is shorter (e.g. CSV missing columns), take what we have.
        slice_len = min(len(tokens) - 2, days_in_month)
        daily_statuses = tokens[-slice_len:]

        # 5. Extract Name (Bidirectional)
        try:
            code_idx = tokens.index(emp_code)

            # Scenario A: ID is at start (PDF style) -> Name is AFTER ID
            if code_idx < 3:
                att_start_idx = len(tokens) - len(daily_statuses)
                name_tokens = tokens[code_idx + 1 : att_start_idx]
                # Filter out 'Sh.', 'Mr.'
                name_tokens = [
                    t
                    for t in name_tokens
                    if t.lower() not in ["sh.", "mr.", "ms.", "mrs.", "lt."]
                ]
                emp_name = " ".join(
                    name_tokens[:3]
                )  # Take first 3 words max to avoid noise

            # Scenario B: ID is in middle (CSV style) -> Name is BEFORE ID
            else:
                # Name is likely the tokens before the ID
                name_tokens = tokens[:code_idx]
                # Filter out 'Mr.' etc
                name_tokens = [
                    t
                    for t in name_tokens
                    if t.lower() not in ["name", "sr.no", "mr.", "ms."]
                ]
                emp_name = " ".join(name_tokens)

            if not emp_name.strip():
                emp_name = "Unknown"

        except (ValueError, IndexError):
            emp_name = "Unknown"

        # 6. Process Days
        for day_idx, status_code in enumerate(daily_statuses):
            day = day_idx + 1
            status_code = status_code.upper()

            erp_status = None

            if status_code in ["P", "p", "0"]:  # '0' often appears in Excel for Present
                continue
            elif status_code == "L":
                erp_status = "On Leave"
            elif status_code == "A":
                erp_status = "Absent"
            elif any(x in status_code for x in ["H", "/", "½", "%", "1/2"]):
                erp_status = "Half Day"
            elif status_code in [
                "-",
                ".",
                "|",
                "_",
                ":",
                ";",
                "I",
                "l",
                "1",
                "NAN",
                "nan",
            ]:
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

        # --- UNIVERSAL ATTENDANCE PARSER ---
        if job.target_doctype.lower() == "attendance":
            # 1. Convert to text
            text_content = extract_text_from_any_file(source_path)

            # Debug log
            print(f"--- EXTRACTED TEXT ({source_path.suffix}) ---")
            print(text_content[:1000])
            print("--- END TEXT ---")

            # 2. Parse text with enhanced regex
            extracted_data = parse_attendance_text(text_content, year=2025, month=10)

        else:
            # Generic logic fallback
            text_content = extract_text_from_any_file(source_path)
            extracted_data = [
                {"extracted_line": l} for l in text_content.splitlines() if l.strip()
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
