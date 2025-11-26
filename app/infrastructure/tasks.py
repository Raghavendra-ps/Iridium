# Iridium-main/app/infrastructure/tasks.py

import asyncio
import json
import shutil
from datetime import datetime
from pathlib import Path

import chardet  # We will use this to detect encodings
import docx
import pandas as pd
import PyPDF2
import pytesseract
from PIL import Image

from app.db.models import ConversionJob, LinkedOrganization
from app.db.session import SessionLocal
from app.infrastructure.celery_app import celery
from app.infrastructure.erpnext_client import ERPNextClient

UPLOAD_DIR = Path("/app/uploads")
PROCESSED_DIR = UPLOAD_DIR / "processed"


@celery.task(bind=True)
def submit_to_erpnext_task(self, job_id: int):
    """
    Submits the validated data from a conversion job to ERPNext, one record at a time.
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
                    response = await erp_client.create_document(
                        job.target_doctype, record
                    )
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
    The main Celery task for file extraction with universal file type support.
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

        # --- Universal File Type Dispatcher ---

        if file_ext in [".xlsx", ".xls"]:
            # Pandas is generally good at handling Excel encodings automatically
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

        elif file_ext == ".csv":
            # --- START: Robust CSV Encoding Handling ---
            try:
                # First, try to read with standard UTF-8
                df_no_header = pd.read_csv(source_path, header=None, encoding="utf-8")
            except UnicodeDecodeError:
                # If UTF-8 fails, try with 'latin-1', which is common for Western European languages
                # and less likely to fail than other encodings.
                df_no_header = pd.read_csv(source_path, header=None, encoding="latin-1")

            header_row_index = 0
            for i, row in df_no_header.iterrows():
                if row.notna().sum() > len(row) / 2:
                    header_row_index = i
                    break

            try:
                df = pd.read_csv(source_path, header=header_row_index, encoding="utf-8")
            except UnicodeDecodeError:
                df = pd.read_csv(
                    source_path, header=header_row_index, encoding="latin-1"
                )

            df.columns = [
                str(c).strip().replace("\n", " ")
                if pd.notna(c) and "Unnamed" not in str(c)
                else f"column_{i + 1}"
                for i, c in enumerate(df.columns)
            ]
            df.dropna(how="all", inplace=True)
            df = df.fillna("").astype(str)
            df.to_json(json_path, orient="records", indent=2, force_ascii=False)
            # --- END: Robust CSV Encoding Handling ---

        elif file_ext == ".json":
            # --- START: Robust JSON Encoding Handling ---
            try:
                with open(source_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except UnicodeDecodeError:
                with open(
                    source_path, "r", encoding="utf-8-sig"
                ) as f:  # Try UTF-8 with BOM
                    data = json.load(f)

            if not isinstance(data, list) or not all(isinstance(i, dict) for i in data):
                raise TypeError("Uploaded JSON must be a list of objects.")
            shutil.copy(source_path, json_path)
            # --- END: Robust JSON Encoding Handling ---

        elif file_ext in [".png", ".jpg", ".jpeg", ".tiff", ".bmp"]:
            text = pytesseract.image_to_string(Image.open(source_path))
            for line in text.splitlines():
                if line.strip():
                    extracted_data.append({"extracted_line": line.strip()})
            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(extracted_data, f, indent=2, ensure_ascii=False)

        elif file_ext == ".pdf":
            text = ""
            with open(source_path, "rb") as f:
                reader = PyPDF2.PdfReader(f)
                for page in reader.pages:
                    page_text = page.extract_text()
                    if page_text:
                        text += page_text + "\n"
            for line in text.splitlines():
                if line.strip():
                    extracted_data.append({"extracted_line": line.strip()})
            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(extracted_data, f, indent=2, ensure_ascii=False)

        elif file_ext == ".docx":
            doc = docx.Document(source_path)
            for para in doc.paragraphs:
                if para.text.strip():
                    extracted_data.append({"extracted_line": para.text.strip()})
            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(extracted_data, f, indent=2, ensure_ascii=False)

        else:
            # For any other file, treat as plain text but with robust encoding detection
            with open(source_path, "rb") as f_binary:
                raw_data = f_binary.read()
                result = chardet.detect(raw_data)
                encoding = result["encoding"] or "utf-8"

            try:
                text_content = raw_data.decode(encoding)
            except (UnicodeDecodeError, TypeError):
                # Fallback to latin-1 if detection fails or is wrong
                text_content = raw_data.decode("latin-1", errors="ignore")

            for line in text_content.splitlines():
                if line.strip():
                    extracted_data.append({"extracted_line": line.strip()})
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
