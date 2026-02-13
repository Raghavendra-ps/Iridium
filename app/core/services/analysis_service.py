import re
from typing import Any, Dict, List, Tuple

import numpy as np  # Import numpy
import pandas as pd

# The internal dictionary of aliases for intelligent matching.
COLUMN_ALIASES = {
    "employee_code": [
        "empl code",
        "emp id",
        "employee code",
        "s.no",
        "employee #",
        "emp code",
    ],
    "employee_name": ["name", "employee name", "full name", "name of employees"],
    "day_start": [str(i) for i in range(1, 6)] + [f"10/{i}" for i in range(1, 6)],
}


def analyze_file_structure(
    df: pd.DataFrame,
) -> Tuple[List[str], Dict[str, Any], List[Dict[str, Any]]]:
    """
    Analyzes a DataFrame to intelligently detect the header row, find columns,
    and generate a suggested parsing configuration.
    """
    best_header_index = 0
    max_score = -1

    for i in range(min(10, len(df))):
        row_values = df.iloc[i].dropna().astype(str)
        if row_values.empty:
            continue

        non_numeric_count = sum(1 for val in row_values if not val.isnumeric())
        uniqueness_score = (
            len(row_values.unique()) / len(row_values) if len(row_values) > 0 else 0
        )
        score = non_numeric_count * uniqueness_score

        if score > max_score:
            max_score = score
            best_header_index = i

    # Clean headers to match logic in read_tabular_file
    raw_headers = df.iloc[best_header_index]
    headers = []
    for h in raw_headers:
        h_str = str(h).strip()
        if ' 00:00:00' in h_str:
            h_str = h_str.replace(' 00:00:00', '')
        headers.append(h_str)
    
    headers = pd.Index(headers)
    data_df = df.iloc[best_header_index + 1 :].copy()
    data_df.columns = headers

    cleaned_headers = {h: h.lower() for h in headers}

    suggestions = {"header_row": best_header_index}
    detected_columns = list(headers)

    for key, aliases in COLUMN_ALIASES.items():
        for header, cleaned_header in cleaned_headers.items():
            if any(alias in cleaned_header for alias in aliases):
                if key == "day_start" and "day_start_col" not in suggestions:
                    suggestions["day_start_col"] = header
                elif key != "day_start" and f"{key}_col" not in suggestions:
                    suggestions[f"{key}_col"] = header

    if "day_start_col" in suggestions:
        try:
            start_index = detected_columns.index(suggestions["day_start_col"])
            day_cols = [
                h
                for h in detected_columns[start_index:]
                if re.match(r"^(\d{1,2}|\d{1,2}/\d{1,2})$", str(h).strip())
            ]
            if day_cols:
                suggestions["day_end_col"] = day_cols[-1]
        except (ValueError, IndexError):
            pass

    # --- START OF FIX: Handle NaN values before serializing to JSON ---
    # Replace all pandas NaN/NaT values with None, which serializes to JSON null.
    preview_df = data_df.head(5).replace({np.nan: None})
    preview_data = preview_df.to_dict(orient="records")
    # --- END OF FIX ---

    return detected_columns, suggestions, preview_data
