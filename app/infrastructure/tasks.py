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

from app.db.models import ConversionJob, LinkedOrganization, MappingProfile
from app.db.session import SessionLocal
from app.infrastructure.celery_app import celery
from app.infrastructure.erpnext_client import ERPNextClient

UPLOAD_DIR = Path("/app/uploads")
PROCESSED_DIR = UPLOAD_DIR / "processed"


# --- INTELLIGENT HELPER FUNCTIONS ---


def normalize_emp_code(code: Any) -> str:
    """
    Sanitizes employee codes by converting to string and stripping whitespace.
    It no longer removes hyphens or other internal characters.
    """
    if not code:
        return ""
    return str(code).strip().upper()


def _clean_emp_name(name: Any) -> str:
    """Removes common salutations from names."""
    if not isinstance(name, str):
        name = str(name)
    return re.sub(r"^(Mr|Ms|Mrs|Sh|W/o)\.?\s*", "", name, flags=re.IGNORECASE).strip()


def find_header_row_intelligent(
    file_path: Path, expected_columns: List[str] = None
) -> int:
    """
    Intelligently finds the header row by looking for the row with maximum valid column names.
    This handles title rows, merged cells, and other Excel formatting issues.
    """
    ext = file_path.suffix.lower()

    try:
        # Read first 20 rows without any header interpretation
        if ext in [".xlsx", ".xls"]:
            df_preview = pd.read_excel(file_path, header=None, nrows=20)
        elif ext == ".csv":
            try:
                df_preview = pd.read_csv(
                    file_path, header=None, nrows=20, encoding="utf-8"
                )
            except UnicodeDecodeError:
                df_preview = pd.read_csv(
                    file_path, header=None, nrows=20, encoding="latin-1"
                )
        else:
            return 0
    except Exception:
        return 0

    best_row = 0
    max_score = 0

    # Common header keywords for attendance sheets
    header_keywords = [
        "empl",
        "employee",
        "code",
        "name",
        "department",
        "designation",
        "date",
        "day",
        "status",
        "present",
        "absent",
        "leave",
        "doj",
    ]

    for idx, row in df_preview.iterrows():
        # Convert row to strings and clean
        row_values = [str(v).strip().lower() for v in row if pd.notna(v)]

        if len(row_values) < 3:  # Header should have at least 3 columns
            continue

        score = 0

        # Score 1: Count non-empty cells
        non_empty = sum(1 for v in row_values if v and v != "nan")
        score += non_empty * 2

        # Score 2: Check for header keywords
        keyword_matches = sum(
            1
            for keyword in header_keywords
            if any(keyword in cell for cell in row_values)
        )
        score += keyword_matches * 15

        # Score 3: Check for expected columns from config
        if expected_columns:
            for expected_col in expected_columns:
                if expected_col:
                    expected_lower = expected_col.lower()
                    if any(expected_lower in cell for cell in row_values):
                        score += 25

        # Score 4: Penalize rows with mostly numbers (likely data rows)
        mostly_numbers = sum(
            1 for v in row_values if v.replace(".", "").isdigit()
        ) / max(len(row_values), 1)
        if mostly_numbers > 0.5:
            score -= 20

        # Score 5: Penalize single long text (title rows like "EHPL-Attendance for...")
        if len(row_values) > 0 and len(row_values[0]) > 30 and non_empty == 1:
            score -= 50

        if score > max_score:
            max_score = score
            best_row = int(idx)

    # Safety check: if best_row is beyond row 15, default to 0
    if best_row > 15:
        best_row = 0

    return best_row


def read_tabular_file(
    file_path: Path,
    header_rows: Optional[List[int]] = None,
    expected_columns: Optional[List[str]] = None,
) -> pd.DataFrame:
    """Reads Excel or CSV into a pandas DataFrame with intelligent header detection."""
    ext = file_path.suffix.lower()

    # Auto-detect header row if not provided
    if header_rows is None or header_rows == [0]:
        detected_row = find_header_row_intelligent(file_path, expected_columns)
        print(f"Auto-detected header row: {detected_row}")
        header_rows = [detected_row]

    # Ensure header_rows is a single integer for pandas
    header_row = header_rows[0] if isinstance(header_rows, list) else header_rows

    df = None
    if ext in [".xlsx", ".xls"]:
        # Prevent pandas from parsing dates in column names
        df = pd.read_excel(file_path, header=header_row, parse_dates=False)
    elif ext == ".csv":
        try:
            df = pd.read_csv(
                file_path,
                encoding="utf-8",
                on_bad_lines="skip",
                header=header_row,
                parse_dates=False,
            )
        except UnicodeDecodeError:
            df = pd.read_csv(
                file_path,
                encoding="latin-1",
                on_bad_lines="skip",
                header=header_row,
                parse_dates=False,
            )
    else:
        raise ValueError(f"Unsupported tabular file format: {ext}")

    # Handle MultiIndex columns
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = [
            " ".join(map(str, col)).replace("Unnamed: 0_level_0", "").strip()
            for col in df.columns.values
        ]

    # Clean column names and remove any datetime formatting
    cleaned_columns: List[str] = []
    for col in df.columns:
        col_str = str(col).strip()

        # If column is a Timestamp object, format as date string
        if isinstance(col, pd.Timestamp):
            col_str = col.strftime("%Y-%m-%d")
        # If it's stringified timestamp-like with midnight, strip time
        elif " 00:00:00" in col_str:
            col_str = col_str.replace(" 00:00:00", "")

        cleaned_columns.append(col_str)

    df.columns = cleaned_columns

    print(
        f"Read DataFrame with columns: {df.columns.tolist()[:5]}... (showing first 5)"
    )
    print(f"DataFrame shape: {df.shape}")
    print(
        f"First row of data: {df.iloc[0].tolist()[:3]}..."
        if len(df) > 0
        else "Empty DataFrame"
    )

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


def find_column_fuzzy(
    df: pd.DataFrame, target_col: str, threshold: float = 0.7
) -> Optional[str]:
    """
    Finds a column in the dataframe that closely matches the target column name.
    Uses fuzzy matching to handle minor variations.
    """
    if not target_col:
        return None

    target_lower = target_col.lower().strip()
    target_words = set(re.findall(r"\w+", target_lower))

    best_match = None
    best_score = 0.0

    for col in df.columns:
        col_lower = str(col).lower().strip()
        col_words = set(re.findall(r"\w+", col_lower))

        # Exact match
        if col_lower == target_lower:
            return str(col)

        # Contains match
        if target_lower in col_lower or col_lower in target_lower:
            score = len(target_lower) / max(len(col_lower), 1)
            if score > best_score:
                best_score = score
                best_match = str(col)

        # Word overlap match
        if target_words and col_words:
            overlap = len(target_words & col_words)
            score = overlap / max(len(target_words), len(col_words))
            if score >= threshold and score > best_score:
                best_score = score
                best_match = str(col)

    return best_match


# --- DYNAMIC PARSING ENGINE ---


def intelligent_parser_engine(
    df: pd.DataFrame,
    config: Dict[str, Any],
    year: int,
    month: int,
    mapping_rules: Dict[str, str] = None,
) -> List[Dict[str, Any]]:
    """
    A single, powerful parser that interprets a DataFrame based on a user-defined template config.
    This version is robust against whitespace, fuzzy column matching, and multi-level headers.
    """
    mode = config.get("mode")
    if not mode:
        raise ValueError("Import template config is missing required 'mode' key.")

    # Clean all column headers
    df.columns = [str(col).strip() for col in df.columns]
    records: List[Dict[str, Any]] = []

    # Debug logging
    print("\n=== PARSER DEBUG ===")
    print(f"Mode: {mode}")
    print(f"Config: {config}")
    print(f"DataFrame shape: {df.shape}")
    print(f"Columns: {df.columns.tolist()}")
    print(f"Mapping rules: {mapping_rules}")
    print("First 3 rows of data:")
    print(df.head(3))

    try:
        if mode == "MATRIX":
            emp_code_col_target = config["employee_code_col"].strip()
            emp_name_col_target = config.get("employee_name_col", "").strip()
            start_col_prefix = config["day_start_col"].strip()
            end_col_prefix = config["day_end_col"].strip()

            if not all(
                [
                    emp_code_col_target,
                    start_col_prefix,
                    end_col_prefix,
                    mapping_rules is not None,
                ]
            ):
                raise ValueError(
                    "MATRIX config is missing required keys or a mapping profile is not linked."
                )

            emp_code_col = find_column_fuzzy(df, emp_code_col_target)
            if not emp_code_col:
                raise KeyError(
                    f"Employee code column '{emp_code_col_target}' not found. "
                    f"Available columns: {df.columns.tolist()}"
                )

            print(f"Found employee code column: '{emp_code_col}'")

            emp_name_col = None
            if emp_name_col_target:
                emp_name_col = find_column_fuzzy(df, emp_name_col_target)
                print(f"Found employee name column: '{emp_name_col}'")

            df_before = len(df)
            df = df.dropna(subset=[emp_code_col])
            print(f"Rows after dropna: {len(df)} (was {df_before})")

            all_cols = df.columns.tolist()
            start_idx = -1
            end_idx = -1

            # Normalize the prefix by removing timestamp portion
            start_prefix_clean = start_col_prefix.replace(" 00:00:00", "").strip()
            end_prefix_clean = end_col_prefix.replace(" 00:00:00", "").strip()

            print(
                f"Looking for start column: '{start_prefix_clean}' (config: '{start_col_prefix}')"
            )
            print(
                f"Looking for end column: '{end_prefix_clean}' (config: '{end_col_prefix}')"
            )

            # Find the first column that matches the start date
            for i, col in enumerate(all_cols):
                col_str = str(col).strip()
                # Check if column matches start date (with or without time)
                if (
                    col_str == start_prefix_clean
                    or col_str.startswith(start_prefix_clean)
                    or col_str == start_col_prefix
                    or col_str.startswith(start_col_prefix)
                ):
                    start_idx = i
                    print(f"Found start column at index {i}: '{col}'")
                    break

            # Find the last column that matches the end date
            for i in range(len(all_cols) - 1, -1, -1):
                col_str = str(all_cols[i]).strip()
                # Check if column matches end date (with or without time)
                if (
                    col_str == end_prefix_clean
                    or col_str.startswith(end_prefix_clean)
                    or col_str == end_col_prefix
                    or col_str.startswith(end_col_prefix)
                ):
                    end_idx = i
                    print(f"Found end column at index {i}: '{all_cols[i]}'")
                    break

            # Fallback: if we found nothing, look for columns after employee columns
            if start_idx == -1:
                emp_col_idx = all_cols.index(emp_code_col)
                start_idx = emp_col_idx + (2 if emp_name_col else 1)
                print(f"Using fallback start index: {start_idx}")

            if end_idx == -1 or end_idx < start_idx:
                end_idx = min(start_idx + 31, len(all_cols) - 1)
                print(f"Using fallback end index: {end_idx}")

            day_columns = df.columns[start_idx : end_idx + 1]

            print(f"Start column index: {start_idx}, End column index: {end_idx}")
            print(f"Day columns ({len(day_columns)}): {day_columns.tolist()}")

            row_count = 0
            for idx, row in df.iterrows():
                emp_code = normalize_emp_code(row[emp_code_col])
                emp_name = (
                    _clean_emp_name(row[emp_name_col])
                    if emp_name_col and emp_name_col in row.index
                    else emp_code
                )

                print(
                    f"Raw emp_code from row {idx}: '{row[emp_code_col]}' -> normalized: '{emp_code}'"
                )

                if not emp_code or emp_code.upper() == "NAN":
                    print(f"  Skipping row {idx}: invalid employee code")
                    continue

                row_count += 1
                print(
                    f"\n--- Processing Employee Row {row_count}: {emp_code} ({emp_name}) ---"
                )

                mapped_count = 0
                skipped_count = 0

                for day_idx, day_header in enumerate(day_columns):
                    # Extract day number from column header - handle YYYY-MM-DD format
                    # THIS IS THE CRITICAL FIX - properly parse date columns
                    day = None
                    day_str = str(day_header).strip()

                    if "-" in day_str:
                        # Date format: YYYY-MM-DD (e.g., "2025-11-01")
                        parts = day_str.split("-")
                        if len(parts) == 3:
                            try:
                                day = int(parts[2])  # Day is the third part
                                if row_count == 1 and day_idx < 5:
                                    print(
                                        f"  Column '{day_header}': Extracted day {day} from YYYY-MM-DD"
                                    )
                            except (ValueError, IndexError):
                                if row_count == 1 and day_idx < 5:
                                    print(
                                        f"  Column '{day_header}': Cannot parse day from date"
                                    )
                                continue
                    elif "/" in day_str:
                        # Date format: DD/MM/YYYY or MM/DD/YYYY
                        parts = day_str.split("/")
                        if len(parts) == 3:
                            try:
                                # Assume DD/MM/YYYY format (first part is day)
                                day = int(parts[0])
                                if row_count == 1 and day_idx < 5:
                                    print(
                                        f"  Column '{day_header}': Extracted day {day} from DD/MM/YYYY"
                                    )
                            except ValueError:
                                if row_count == 1 and day_idx < 5:
                                    print(
                                        f"  Column '{day_header}': Cannot parse day from date"
                                    )
                                continue
                    else:
                        # Plain number like "1", "2", "01", "02"
                        day_match = re.search(r"^(\d+)$", day_str)
                        if day_match:
                            try:
                                day = int(day_match.group(1))
                                if row_count == 1 and day_idx < 5:
                                    print(
                                        f"  Column '{day_header}': Extracted day {day} from plain number"
                                    )
                            except ValueError:
                                continue

                    # Skip invalid days
                    if day is None or day < 1 or day > 31:
                        if row_count == 1 and day_idx < 5:
                            print(
                                f"  Column '{day_header}': Day {day} out of range (1-31)"
                            )
                        continue

                    cell_value = row[day_header]
                    code = str(cell_value).strip().upper()

                    if row_count == 1 and day_idx < 5:
                        print(
                            f"  Day {day} ({day_header}): "
                            f"raw_value={repr(cell_value)}, "
                            f"type={type(cell_value).__name__}, "
                            f"code='{code}'"
                        )

                    if not code or code in ["NAN", "NONE", ""]:
                        if row_count == 1 and day_idx < 5:
                            print(f"    -> Empty, skipping")
                        skipped_count += 1
                        continue

                    target_status = mapping_rules.get(code) if mapping_rules else None

                    if row_count == 1 and day_idx < 10:
                        print(
                            f"    -> Lookup: code='{code}' in rules? {code in mapping_rules if mapping_rules else False} "
                            f"-> status='{target_status}'"
                        )

                    if target_status and target_status != "IGNORE":
                        try:
                            date = f"{year}-{month:02d}-{day:02d}"
                            datetime.strptime(date, "%Y-%m-%d")

                            if row_count == 1 and day_idx < 10:
                                print(f"    -> ✓ MAPPED: {date} = {target_status}")

                            records.append(
                                {
                                    "employee": emp_code,
                                    "employee_name": emp_name,
                                    "attendance_date": date,
                                    "status": target_status,
                                }
                            )
                            mapped_count += 1
                        except (ValueError, TypeError) as e:
                            if row_count == 1 and day_idx < 5:
                                print(f"    -> Date validation failed: {e}")
                            continue
                    else:
                        if row_count == 1 and day_idx < 10:
                            print(f"    -> Ignored (status={target_status})")

                if row_count <= 2:
                    print(
                        f"Employee {emp_code}: Processed {len(day_columns)} days, "
                        f"Skipped {skipped_count} empty, Mapped {mapped_count} records"
                    )

            print(f"Total records extracted: {len(records)}")
            print("===================\n")

        elif mode == "SUMMARY":
            emp_code_col_target = config["employee_code_col"].strip()
            emp_name_col_target = config.get("employee_name_col", "").strip()
            status_map = config.get("status_column_map", {})

            emp_code_col = find_column_fuzzy(df, emp_code_col_target)
            if not emp_code_col:
                raise KeyError(
                    f"Employee code column '{emp_code_col_target}' not found. "
                    f"Available columns: {df.columns.tolist()}"
                )

            emp_name_col = None
            if emp_name_col_target:
                emp_name_col = find_column_fuzzy(df, emp_name_col_target)

            df = df.dropna(subset=[emp_code_col])

            days_in_month = (
                (datetime(year, month + 1, 1) - timedelta(days=1)).day
                if month < 12
                else 31
            )

            for _, row in df.iterrows():
                emp_code = normalize_emp_code(row[emp_code_col])
                emp_name = (
                    _clean_emp_name(row[emp_name_col])
                    if emp_name_col and emp_name_col in row.index
                    else emp_code
                )
                if not emp_code or emp_code.upper() == "NAN":
                    continue

                available_days = list(range(1, days_in_month + 1))

                for status, column_name in status_map.items():
                    matched_col = find_column_fuzzy(df, column_name)
                    if matched_col:
                        try:
                            count = int(float(row[matched_col]))
                            for _ in range(count):
                                if not available_days:
                                    break
                                day = available_days.pop(0)
                                date = f"{year}-{month:02d}-{day:02d}"
                                records.append(
                                    {
                                        "employee": emp_code,
                                        "employee_name": emp_name,
                                        "attendance_date": date,
                                        "status": status,
                                    }
                                )
                        except (ValueError, TypeError):
                            continue
        else:
            raise ValueError(f"Unsupported parsing mode: '{mode}'")

    except KeyError as e:
        raise KeyError(
            f"Configuration error: {e}. Available columns are: {df.columns.tolist()}"
        ) from e

    return records


# --- MAIN CELERY TASK ---


@celery.task
def process_file_task(job_id: int):
    """
    Main Celery task that uses the user-confirmed parsing config stored on the job.
    """
    db = SessionLocal()
    job = None

    try:
        job = db.query(ConversionJob).filter(ConversionJob.id == job_id).first()
        if not job:
            return

        job.status = "PROCESSING"
        db.commit()

        source_path = UPLOAD_DIR / job.storage_filename
        PROCESSED_DIR.mkdir(exist_ok=True)
        raw_json_path = PROCESSED_DIR / f"{source_path.stem}_raw.json"
        processed_json_path = PROCESSED_DIR / f"{source_path.stem}_processed.json"

        if not job.parsing_config:
            raise ValueError("Job is missing its parsing configuration.")

        expected_columns: List[str] = []
        if "employee_code_col" in job.parsing_config:
            expected_columns.append(job.parsing_config["employee_code_col"])
        if "employee_name_col" in job.parsing_config:
            expected_columns.append(job.parsing_config.get("employee_name_col", ""))

        header_rows_config = job.parsing_config.get("header_rows")
        header_rows = None
        if header_rows_config:
            header_rows = [
                int(i.strip())
                for i in str(header_rows_config).split(",")
                if i.strip().isdigit()
            ]

        file_ext = source_path.suffix.lower()
        if file_ext in [".xlsx", ".xls", ".csv"]:
            df = read_tabular_file(
                source_path,
                header_rows=header_rows,
                expected_columns=expected_columns,
            )
        else:
            df = ocr_to_dataframe(source_path)

        # Replace numpy NaN with None for JSON compatibility
        df_for_json = df.replace({np.nan: None})
        df_for_json.to_json(raw_json_path, orient="records", indent=2)

        mapping_rules: Dict[str, str] = {}
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

        if job.target_doctype and job.target_doctype.lower() == "attendance":
            if not job.attendance_year or not job.attendance_month:
                raise ValueError("Attendance job is missing Year or Month.")

            extracted_data = intelligent_parser_engine(
                df=df,
                config=job.parsing_config,
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

    except Exception as e:
        if job:
            db.rollback()
            job.status = "EXTRACTION_FAILED"
            job.error_log = {"step": "extraction", "message": str(e)}
            db.commit()
        raise

    finally:
        db.close()


# --- SUBMISSION TASK ---


@celery.task(bind=True)
def submit_to_erpnext_task(
    self, job_id: int, employee_map: Optional[Dict[str, str]] = None
):
    """
    Submits the validated data to ERPNext.

    Args:
        job_id: The conversion job ID
        employee_map: Optional mapping of company employee codes to ERPNext employee IDs
                     Example: {"EHPL002": "HR-EMP-00001", "EHPL013": "HR-EMP-00002"}
                     If not provided, uses the employee codes from the file directly.
    """
    db = SessionLocal()
    job = None

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
            raise ValueError(f"Target organization not found for job {job_id}")

        job.status = "SUBMITTING"
        db.commit()

        with open(job.processed_data_path, "r", encoding="utf-8") as f:
            records = json.load(f)

        erp_client = ERPNextClient(
            base_url=target_org.erpnext_url,
            api_key=target_org.api_key,
            api_secret=target_org.api_secret,
        )

        total_records = len(records)
        success_count = 0
        errors = []

        print(f"\n=== STARTING SUBMISSION FOR JOB {job_id} ===")
        print(f"Total records to submit: {total_records}")
        print(
            f"Employee mapping provided: {'Yes' if employee_map else 'No (using codes from file)'}"
        )
        if employee_map:
            print(f"Employee map contains {len(employee_map)} mappings")
            print(f"Sample mappings: {dict(list(employee_map.items())[:3])}")

        async def run_submission():
            nonlocal success_count, errors

            for i, record in enumerate(records):
                error_message = None
                original_emp_code = record.get("employee")

                try:
                    # If employee_map is provided, use it to map to ERPNext employee ID
                    if employee_map:
                        erpnext_employee_id = employee_map.get(original_emp_code)
                        if not erpnext_employee_id:
                            raise ValueError(
                                f"Employee code '{original_emp_code}' not found in mapping. "
                                f"Available codes: {list(employee_map.keys())[:10]}..."
                            )
                        if i < 5:  # Debug first 5 records
                            print(
                                f"  Record {i + 1}: Mapped '{original_emp_code}' -> '{erpnext_employee_id}'"
                            )
                    else:
                        # Use the employee code from the file directly
                        erpnext_employee_id = original_emp_code
                        if i < 5:
                            print(
                                f"  Record {i + 1}: Using employee code '{erpnext_employee_id}' as-is"
                            )

                    payload = {
                        "employee": erpnext_employee_id,
                        "attendance_date": record.get("attendance_date"),
                        "status": record.get("status"),
                        "docstatus": 1,
                    }
                    if record.get("employee_name"):
                        payload["employee_name"] = record.get("employee_name")

                    response = await erp_client.create_document("Attendance", payload)
                    response.raise_for_status()
                    success_count += 1

                except httpx.HTTPStatusError as e:
                    try:
                        error_data = e.response.json()
                        if "_server_messages" in error_data:
                            messages = json.loads(error_data["_server_messages"])
                            error_message = ". ".join(
                                [
                                    str(m.get("message", m))
                                    for m in messages
                                    if isinstance(m, dict)
                                ]
                                + [str(m) for m in messages if isinstance(m, str)]
                            )
                        elif "exception" in error_data:
                            error_message = error_data.get("exception")
                        else:
                            error_message = str(error_data)
                    except (json.JSONDecodeError, KeyError):
                        error_message = e.response.text[:500]

                except Exception as e:
                    error_message = str(e)

                if error_message:
                    errors.append(
                        {
                            "record_index": i,
                            "record_data": record,
                            "original_code": original_emp_code,
                            "mapped_code": employee_map.get(original_emp_code)
                            if employee_map
                            else original_emp_code,
                            "error": error_message,
                        }
                    )
                    if i < 10:  # Print first 10 errors
                        print(f"  ❌ Record {i + 1} FAILED: {error_message}")

                self.update_state(
                    state="PROGRESS",
                    meta={"current": i + 1, "total": total_records},
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

        summary = f"Submission for job {job.id} finished. Success: {success_count}/{total_records}."
        print(f"\n=== {summary} ===\n")
        return summary

    except Exception as e:
        if job:
            db.rollback()
            job.status = "SUBMISSION_FAILED"
            job.error_log = {"step": "submission_setup", "message": str(e)}
            db.commit()
        raise

    finally:
        db.close()
