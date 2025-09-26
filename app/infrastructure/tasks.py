import json
import shutil
from pathlib import Path
import pandas as pd
import pytesseract
from PIL import Image
import PyPDF2
import docx

from app.infrastructure.celery_app import celery
from app.db.session import SessionLocal
from app.db.models import ConversionJob

UPLOAD_DIR = Path("/app/uploads")
PROCESSED_DIR = UPLOAD_DIR / "processed"

@celery.task
def process_file_task(job_id: int):
    """
    The main Celery task for file extraction with universal file type support.
    """
    db = SessionLocal()
    job = db.query(ConversionJob).filter(ConversionJob.id == job_id).first()
    if not job: return f"Job {job_id} not found."

    try:
        job.status = "PROCESSING"
        db.commit()

        source_path = UPLOAD_DIR / job.storage_filename
        PROCESSED_DIR.mkdir(exist_ok=True)

        json_path = PROCESSED_DIR / f"{source_path.stem}.json"
        file_ext = source_path.suffix.lower()
        extracted_data = []

        # --- Universal File Type Dispatcher ---

        if file_ext in ['.xlsx', '.xls']:
            # Handle Excel files with advanced header detection
            df_no_header = pd.read_excel(source_path, header=None)
            header_row_index = 0
            for i, row in df_no_header.iterrows():
                if row.notna().sum() > len(row) / 2:
                    header_row_index = i
                    break
            df = pd.read_excel(source_path, header=header_row_index)
            df.columns = [str(c).strip().replace('\n', ' ') if pd.notna(c) and 'Unnamed' not in str(c) else f'column_{i+1}' for i, c in enumerate(df.columns)]
            df.dropna(how='all', inplace=True)
            df = df.fillna('').astype(str)
            df.to_json(json_path, orient='records', indent=2, force_ascii=False)

        elif file_ext == '.csv':
            # Handle CSV files with advanced header detection
            df_no_header = pd.read_csv(source_path, header=None)
            header_row_index = 0
            for i, row in df_no_header.iterrows():
                if row.notna().sum() > len(row) / 2:
                    header_row_index = i
                    break
            df = pd.read_csv(source_path, header=header_row_index)
            df.columns = [str(c).strip().replace('\n', ' ') if pd.notna(c) and 'Unnamed' not in str(c) else f'column_{i+1}' for i, c in enumerate(df.columns)]
            df.dropna(how='all', inplace=True)
            df = df.fillna('').astype(str)
            df.to_json(json_path, orient='records', indent=2, force_ascii=False)

        elif file_ext == '.json':
            # Handle pre-formatted JSON
            with open(source_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                if not isinstance(data, list) or not all(isinstance(i, dict) for i in data):
                    raise TypeError("Uploaded JSON must be a list of objects.")
            shutil.copy(source_path, json_path)

        elif file_ext in ['.png', '.jpg', '.jpeg', '.tiff', '.bmp']:
            # Handle images with OCR
            text = pytesseract.image_to_string(Image.open(source_path))
            for line in text.splitlines():
                if line.strip(): extracted_data.append({"extracted_line": line.strip()})
            with open(json_path, 'w', encoding='utf-8') as f:
                json.dump(extracted_data, f, indent=2, ensure_ascii=False)

        elif file_ext == '.pdf':
            # Handle PDFs
            text = ""
            with open(source_path, "rb") as f:
                reader = PyPDF2.PdfReader(f)
                for page in reader.pages:
                    page_text = page.extract_text()
                    if page_text: text += page_text + "\n"
            for line in text.splitlines():
                if line.strip(): extracted_data.append({"extracted_line": line.strip()})
            with open(json_path, 'w', encoding='utf-8') as f:
                json.dump(extracted_data, f, indent=2, ensure_ascii=False)

        elif file_ext == '.docx':
            # Handle Word documents
            doc = docx.Document(source_path)
            for para in doc.paragraphs:
                 if para.text.strip(): extracted_data.append({"extracted_line": para.text.strip()})
            with open(json_path, 'w', encoding='utf-8') as f:
                json.dump(extracted_data, f, indent=2, ensure_ascii=False)

        else:
            # --- THE CATCH-ALL FALLBACK ---
            # Treat any other file type as plain text.
            try:
                with open(source_path, 'r', encoding='utf-8', errors='ignore') as f:
                    for line in f:
                        if line.strip():
                            extracted_data.append({"extracted_line": line.strip()})
                with open(json_path, 'w', encoding='utf-8') as f:
                    json.dump(extracted_data, f, indent=2, ensure_ascii=False)
            except Exception as text_e:
                # If it can't even be read as text, then we fail gracefully.
                raise ValueError(f"File type '{file_ext}' is not a known structured or text-based format. Error: {text_e}")


        # Final database update
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
