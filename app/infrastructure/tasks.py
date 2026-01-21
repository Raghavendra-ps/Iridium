import asyncio
import json
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

import docx
import httpx
import numpy as np
import pandas as pd
import PyPDF2
import pytesseract
from pdf2image import convert_from_path
from PIL import Image
from sqlalchemy.orm import joinedload

from app.db.models import (ConversionJob, LinkedOrganization,
                           MappingProfile)
from app.db.session import SessionLocal
from app.infrastructure.celery_app import celery
from app.infrastructure.erpnext_client import ERPNextClient

UPLOAD_DIR = Path("/app/uploads")
PROCESSED_DIR = UPLOAD_DIR / "processed"


# --- INTELLIGENT HELPER FUNCTIONS ---

def _normalize_emp_code(code: Any) -> str:
    """Removes common separators and cleans employee codes."""
    if not isinstance(code, str):
        code = str(code)
    return re.sub(r"[\s_-]", "", code).upper()


def _clean_emp_name(name: Any) -> str:
    """Removes common salutations from names."""
    if not isinstance(name, str):
        name = str(name)
    return re.sub(r"^(Mr|Ms|Mrs|Sh|W/o)\.?\s*", "", name, flags=re.IGNORECASE).strip()


def find_header_row_intelligent(file_path: Path, expected_columns: List[str] = None) -> int:
    """
    Intelligently finds the header row by looking for the row with maximum valid column names.
    """
    ext = file_path.suffix.lower()
    df_preview = None
    try:
        if ext in [".xlsx", ".xls"]:
            df_preview = pd.read_excel(file_path, header=None, nrows=20)
        elif ext == ".csv":
            df_preview = pd.read_csv(file_path, header=None, nrows=20, encoding="utf-8", on_bad_lines='skip')
        else:
            return 0
    except Exception:
        return 0
    
    best_row = 0
    max_score = -1
    
    header_keywords = [
        'empl', 'employee', 'code', 'name', 'department', 'designation',
        'date', 'day', 'status', 'present', 'absent', 'leave', 'doj'
    ]
    
    for idx, row in df_preview.iterrows():
        row_values = [str(v).strip().lower() for v in row if pd.notna(v)]
        if len(row_values) < 3: continue
        
        score = 0
        non_empty = sum(1 for v in row_values if v and v != 'nan')
        score += non_empty * 2
        
        keyword_matches = sum(1 for keyword in header_keywords if any(keyword in cell for cell in row_values))
        score += keyword_matches * 15
        
        if expected_columns:
            for expected_col in expected_columns:
                if expected_col and any(expected_col.lower() in cell for cell in row_values):
                    score += 25
        
        mostly_numbers = sum(1 for v in row_values if v.replace('.', '', 1).isdigit()) / max(len(row_values), 1)
        if mostly_numbers > 0.5: score -= 20
        
        if len(row_values) > 0 and len(row_values[0]) > 30 and non_empty == 1: score -= 50
        
        if score > max_score:
            max_score = score
            best_row = int(idx)
    
    return best_row if best_row < 15 else 0


def read_tabular_file(file_path: Path, header_rows: Optional[List[int]] = None, expected_columns: Optional[List[str]] = None) -> pd.DataFrame:
    """Reads Excel or CSV into a pandas DataFrame with intelligent header detection and cleaning."""
    ext = file_path.suffix.lower()
    
    if header_rows is None:
        detected_row = find_header_row_intelligent(file_path, expected_columns)
        print(f"Auto-detected header row: {detected_row}")
        header_rows = [detected_row]
    
    header_row = header_rows[0] if isinstance(header_rows, list) else header_rows
    
    df = None
    if ext in [".xlsx", ".xls"]:
        df = pd.read_excel(file_path, header=header_row)
    elif ext == ".csv":
        df = pd.read_csv(file_path, encoding="utf-8", on_bad_lines="skip", header=header_row)
    else:
        raise ValueError(f"Unsupported tabular file format: {ext}")

    if isinstance(df.columns, pd.MultiIndex):
        df.columns = [" ".join(map(str, col)).replace("Unnamed: 0_level_0", "").strip() for col in df.columns.values]
    
    cleaned_columns = []
    for col in df.columns:
        if isinstance(col, (datetime, pd.Timestamp)):
            col_str = col.strftime('%Y-%m-%d')
        else:
            col_str = str(col).strip()
            if ' 00:00:00' in col_str:
                col_str = col_str.replace(' 00:00:00', '')
        cleaned_columns.append(col_str)
    
    df.columns = cleaned_columns
    return df


def ocr_to_dataframe(file_path: Path) -> pd.DataFrame:
    """Converts a PDF, Image, or DOCX file to a text block, then heuristically to a DataFrame."""
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

    lines = [re.split(r'\s{2,}', line.strip()) for line in text.splitlines() if line.strip()]
    if not lines:
        return pd.DataFrame()
    
    header_candidate = max(lines, key=len)
    header_len = len(header_candidate)
    data = [line for line in lines if len(line) >= header_len - 1 and len(line) <= header_len + 1]
    return pd.DataFrame(data, columns=header_candidate if data else None)


def find_column_fuzzy(df: pd.DataFrame, target_col: str) -> Optional[str]:
    """Finds a column in the dataframe that closely matches the target column name."""
    if not target_col: return None
    target_lower = target_col.lower().strip()
    target_words = set(re.findall(r'\w+', target_lower))
    best_match = None
    best_score = 0.0
    for col in df.columns:
        col_lower = str(col).lower().strip()
        if col_lower == target_lower: return str(col)
        if target_lower in col_lower or col_lower in target_lower:
            score = len(target_lower) / max(len(col_lower), 1)
            if score > best_score:
                best_score = score
                best_match = str(col)
        if target_words and (col_words := set(re.findall(r'\w+', col_lower))):
            overlap = len(target_words & col_words)
            score = overlap / max(len(target_words), len(col_words))
            if score >= 0.7 and score > best_score:
                best_score = score
                best_match = str(col)
    return best_match


def apply_business_rules(df: pd.DataFrame, config: Dict[str, Any]) -> pd.DataFrame:
    """Applies user-defined business rules to the DataFrame before parsing."""
    rules = config.get("business_rules")
    if not rules or not isinstance(rules, list):
        return df

    print(f"Applying {len(rules)} business rule(s)...")
    df_copy = df.copy()

    for rule in rules:
        if rule.get("type") == "CONVERT_SHORT_LEAVE":
            try:
                sl_col_target = rule.get("short_leave_col")
                leave_col_target = rule.get("full_leave_col")
                conversion_rate = int(rule.get("conversion_rate", 0))

                sl_col_name = find_column_fuzzy(df_copy, sl_col_target)
                leave_col_name = find_column_fuzzy(df_copy, leave_col_target)

                if not all([sl_col_name, leave_col_name, conversion_rate > 0]):
                    print(f"  -> Skipping rule: Invalid configuration provided. SL:'{sl_col_target}', Leave:'{leave_col_target}', Rate:'{conversion_rate}'")
                    continue

                print(f"  -> Applying rule: {conversion_rate} '{sl_col_name}' = 1 '{leave_col_name}'")
                
                df_copy[sl_col_name] = pd.to_numeric(df_copy[sl_col_name], errors='coerce').fillna(0)
                df_copy[leave_col_name] = pd.to_numeric(df_copy[leave_col_name], errors='coerce').fillna(0)

                new_full_leaves = df_copy[sl_col_name] // conversion_rate
                remaining_short_leaves = df_copy[sl_col_name] % conversion_rate

                df_copy[leave_col_name] += new_full_leaves
                df_copy[sl_col_name] = remaining_short_leaves
            except (KeyError, ValueError, TypeError) as e:
                print(f"  -> Skipping rule due to error: {e}")
                continue
    
    return df_copy


def intelligent_parser_engine(df: pd.DataFrame, config: Dict[str, Any], year: int, month: int, mapping_rules: Dict[str, str] = None) -> List[Dict[str, Any]]:
    """A single, powerful parser that interprets a DataFrame based on a user-defined template config."""
    mode = config.get("mode")
    if not mode: raise ValueError("Parsing config is missing required 'mode' key.")

    df.columns = [str(col).strip() for col in df.columns]
    records = []

    try:
        if mode == "MATRIX":
            emp_code_col_target = config["employee_code_col"].strip()
            emp_name_col_target = config.get("employee_name_col", "").strip()
            start_col_prefix = config["day_start_col"].strip()
            end_col_prefix = config["day_end_col"].strip()
            
            emp_code_col = find_column_fuzzy(df, emp_code_col_target)
            if not emp_code_col: raise KeyError(f"Employee code column '{emp_code_col_target}' not found.")
            emp_name_col = find_column_fuzzy(df, emp_name_col_target) if emp_name_col_target else None

            if not all([emp_code_col, start_col_prefix, end_col_prefix, mapping_rules is not None]):
                raise ValueError("MATRIX config is missing required keys or a mapping profile is not linked.")

            df = df.dropna(subset=[emp_code_col])
            
            all_cols = df.columns.tolist()
            start_idx, end_idx = -1, -1
            for i, col in enumerate(all_cols):
                if str(col).startswith(start_col_prefix):
                    start_idx = i
                    break
            for i in range(len(all_cols) - 1, -1, -1):
                if str(all_cols[i]).startswith(end_col_prefix):
                    end_idx = i
                    break
            
            if start_idx == -1: raise KeyError(f"Could not find a column starting with '{start_col_prefix}'")
            if end_idx == -1: raise KeyError(f"Could not find a column starting with '{end_col_prefix}'")
            
            day_columns = df.columns[start_idx : end_idx + 1]

            for _, row in df.iterrows():
                emp_code = _normalize_emp_code(row[emp_code_col])
                emp_name = _clean_emp_name(row.get(emp_name_col)) if emp_name_col and emp_name_col in row.index else emp_code
                if not emp_code or emp_code.upper() == 'NAN': continue
                
                for day_header in day_columns:
                    day_match = re.search(r'(\d+)(?!.*\d)', str(day_header))
                    if not day_match: continue
                    day = int(day_match.group(1))
                    
                    code = str(row[day_header]).strip().upper()
                    target_status = mapping_rules.get(code)
                    
                    if target_status and target_status != "IGNORE":
                        try:
                            date = f"{year}-{month:02d}-{day:02d}"
                            datetime.strptime(date, "%Y-%m-%d")
                            records.append({"employee": emp_code, "employee_name": emp_name, "attendance_date": date, "status": target_status})
                        except (ValueError, TypeError): continue

        elif mode == "SUMMARY":
            emp_code_col_target = config["employee_code_col"].strip()
            emp_name_col_target = config.get("employee_name_col", "").strip()
            status_map = config.get("status_column_map", {})
            emp_code_col = find_column_fuzzy(df, emp_code_col_target)
            if not emp_code_col: raise KeyError(f"Employee code column '{emp_code_col_target}' not found.")
            emp_name_col = find_column_fuzzy(df, emp_name_col_target) if emp_name_col_target else None

            df = df.dropna(subset=[emp_code_col])
            days_in_month = (datetime(year, month + 1, 1) - timedelta(days=1)).day if month < 12 else 31
            for _, row in df.iterrows():
                emp_code = _normalize_emp_code(row[emp_code_col])
                emp_name = _clean_emp_name(row[emp_name_col]) if emp_name_col and emp_name_col in row.index else emp_code
                if not emp_code or emp_code.upper() == 'NAN': continue
                available_days = list(range(1, days_in_month + 1))
                for status, column_name in status_map.items():
                    matched_col = find_column_fuzzy(df, column_name)
                    if matched_col:
                        try:
                            count = int(float(row[matched_col]))
                            for _ in range(count):
                                if not available_days: break
                                day = available_days.pop(0)
                                date = f"{year}-{month:02d}-{day:02d}"
                                records.append({"employee": emp_code, "employee_name": emp_name, "attendance_date": date, "status": status})
                        except (ValueError, TypeError): continue
        else:
            raise ValueError(f"Unsupported parsing mode: '{mode}'")
            
    except KeyError as e:
        raise KeyError(f"Configuration error: {e}. Available columns are: {df.columns.tolist()}") from e
        
    return records


@celery.task
def process_file_task(job_id: int):
    db = SessionLocal()
    job = None
    try:
        job = db.query(ConversionJob).filter(ConversionJob.id == job_id).first()
        if not job: return

        job.status = "PROCESSING"; db.commit()

        source_path = UPLOAD_DIR / job.storage_filename
        PROCESSED_DIR.mkdir(exist_ok=True)
        raw_json_path = PROCESSED_DIR / f"{source_path.stem}_raw.json"
        processed_json_path = PROCESSED_DIR / f"{source_path.stem}_processed.json"
        
        if not job.parsing_config: raise ValueError("Job is missing its parsing configuration.")
        
        expected_cols = [job.parsing_config.get("employee_code_col"), job.parsing_config.get("employee_name_col")]
        header_rows_config = job.parsing_config.get("header_rows")
        header_rows = [int(i.strip()) for i in str(header_rows_config).split(',')] if header_rows_config else None

        file_ext = source_path.suffix.lower()
        if file_ext in ['.xlsx', '.xls', '.csv']:
            df = read_tabular_file(source_path, header_rows=header_rows, expected_columns=expected_cols)
        else:
            df = ocr_to_dataframe(source_path)
        
        if job.parsing_config:
            df = apply_business_rules(df, job.parsing_config)
        
        df_for_json = df.replace({np.nan: None})
        df_for_json.to_json(raw_json_path, orient='records', indent=2)

        mapping_rules = {}
        if job.mapping_profile_id:
            profile = db.query(MappingProfile).options(joinedload(MappingProfile.mappings)).filter(MappingProfile.id == job.mapping_profile_id).first()
            if profile: mapping_rules = {m.source_code.upper(): m.target_status for m in profile.mappings}
        
        if job.target_doctype.lower() == "attendance":
            if not job.attendance_year or not job.attendance_month: raise ValueError("Attendance job is missing Year or Month.")
            extracted_data = intelligent_parser_engine(df=df, config=job.parsing_config, year=job.attendance_year, month=job.attendance_month, mapping_rules=mapping_rules)
        else:
            extracted_data = df.to_dict(orient='records')

        with open(processed_json_path, "w", encoding="utf-8") as f:
            json.dump(extracted_data, f, indent=2, ensure_ascii=False)
        job.raw_data_path = str(raw_json_path)
        job.processed_data_path = str(processed_json_path)
        job.status = "AWAITING_VALIDATION"
        db.commit()

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
def submit_to_erpnext_task(self, job_id: int, employee_map: Dict[str, str]):
    db = SessionLocal()
    job = None
    try:
        job = db.query(ConversionJob).filter(ConversionJob.id == job_id).first()
        if not job: return f"Job {job_id} not found."
        target_org = db.query(LinkedOrganization).filter(LinkedOrganization.id == job.target_org_id).first()
        if not target_org: raise ValueError(f"Target organization not found for job {job_id}")
        job.status = "SUBMITTING"
        db.commit()
        with open(job.processed_data_path, "r", encoding="utf-8") as f: records = json.load(f)
        erp_client = ERPNextClient(base_url=target_org.erpnext_url, api_key=target_org.api_key, api_secret=target_org.api_secret)
        total_records, success_count, errors = len(records), 0, []
        
        async def run_submission():
            nonlocal success_count, errors
            for i, record in enumerate(records):
                error_message = None
                original_emp_code = record.get("employee")
                try:
                    erpnext_employee_id = employee_map.get(original_emp_code)
                    if not erpnext_employee_id: raise ValueError(f"Employee code '{original_emp_code}' not in map.")
                    payload = {"employee": erpnext_employee_id, "attendance_date": record.get("attendance_date"), "status": record.get("status"), "docstatus": 1}
                    if record.get("employee_name"): payload["employee_name"] = record.get("employee_name")
                    response = await erp_client.create_document("Attendance", payload)
                    response.raise_for_status()
                    success_count += 1
                except httpx.HTTPStatusError as e:
                    try:
                        error_data = e.response.json()
                        if "_server_messages" in error_data:
                            messages = json.loads(error_data["_server_messages"])
                            error_message = ". ".join([str(m.get("message", m)) for m in messages if isinstance(m, dict)] + [str(m) for m in messages if isinstance(m, str)])
                        elif "exception" in error_data: error_message = error_data.get("exception")
                        else: error_message = str(error_data)
                    except (json.JSONDecodeError, KeyError): error_message = e.response.text[:500]
                except Exception as e: error_message = str(e)
                if error_message: errors.append({"record_index": i, "record_data": record, "error": error_message})
                self.update_state(state='PROGRESS', meta={'current': i + 1, 'total': total_records})
        asyncio.run(run_submission())

        if errors:
            job.status = "SUBMISSION_FAILED"
            job.error_log = {"step": "submission", "summary": f"{len(errors)} of {total_records} records failed.", "details": errors}
        else:
            job.status = "COMPLETED"
        job.completed_at = datetime.utcnow()
        db.commit()
        return f"Submission for job {job.id} finished. Success: {success_count}/{total_records}."
    except Exception as e:
        if job:
            db.rollback()
            job.status = "SUBMISSION_FAILED"
            job.error_log = {"step": "submission_setup", "message": str(e)}
            db.commit()
        raise e
    finally:
        db.close()