# Iridium-main/app/core/import_config.py

from typing import Any, Dict, List

# Define the supported Import Types
IMPORT_TYPES = {
    "attendance": {
        "label": "Attendance (Monthly Sheet)",
        "doctype": "Attendance",
        # These columns define the Handsontable grid structure
        "columns": [
            {"data": "employee", "title": "Employee ID", "type": "text"},
            {
                "data": "employee_name",
                "title": "Employee Name",
                "type": "text",
                "readOnly": True,
            },
            {
                "data": "attendance_date",
                "title": "Date (YYYY-MM-DD)",
                "type": "date",
                "dateFormat": "YYYY-MM-DD",
            },
            {
                "data": "status",
                "title": "Status",
                "type": "dropdown",
                "source": ["Present", "Absent", "On Leave", "Half Day"],
            },
            {"data": "shift", "title": "Shift", "type": "text"},
            {"data": "leave_type", "title": "Leave Type", "type": "text"},
        ],
        # Only these statuses will be processed by default
        "filter_logic": ["Absent", "On Leave", "Half Day"],
    },
    "generic": {
        "label": "Generic / Other",
        "doctype": "Generic",
        "columns": [
            {"data": "extracted_line", "title": "Extracted Data", "type": "text"}
        ],
    },
}


def get_import_config(import_type: str) -> Dict[str, Any]:
    return IMPORT_TYPES.get(import_type, IMPORT_TYPES["generic"])
