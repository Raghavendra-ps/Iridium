from typing import Any, Dict, List

import httpx


class ERPNextClient:
    """
    A client for making authenticated API requests to an ERPNext instance.
    """

    def __init__(self, base_url: str, api_key: str, api_secret: str):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.api_secret = api_secret
        self.auth_header = f"token {self.api_key}:{self.api_secret}"
        # Initialize a persistent client configured to only use HTTP/1.1
        self.client = httpx.AsyncClient(http1=True, http2=False)

    async def create_document(
        self, doctype: str, data: Dict[str, Any]
    ) -> httpx.Response:
        """
        Creates a new document in ERPNext.
        """
        payload = data
        url = f"{self.base_url}/api/resource/{doctype}"

        headers = {
            "Authorization": self.auth_header,
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

        response = await self.client.post(
            url, json=payload, headers=headers, timeout=30.0
        )
        return response

    # --- START OF NEW FUNCTION ---
    async def get_all_employees(self) -> List[Dict[str, Any]]:
        """
        Fetches all 'Enabled' employees from ERPNext.

        Handles pagination to retrieve the full list. Fetches only the fields
        necessary for mapping.
        """
        all_employees = []
        page_start = 0
        page_length = 1000  # Fetch in batches of 1000

        while True:
            # Define the fields to fetch from the Employee Doctype
            # 'name' is the primary key (e.g., HR-EMP-0001)
            # 'employee_name' is the full name
            # 'company_employee_id' is a custom field often used for old/external IDs
            params = {
                "fields": '["name", "employee_name", "company_employee_id"]',
                "filters": '[["status", "=", "Active"]]',
                "limit_page_length": page_length,
                "limit_start": page_start,
            }
            url = f"{self.base_url}/api/resource/Employee"
            headers = {"Authorization": self.auth_header}

            response = await self.client.get(
                url, headers=headers, params=params, timeout=60.0
            )
            response.raise_for_status()

            data = response.json().get("data", [])
            if not data:
                break  # No more data to fetch, exit the loop

            all_employees.extend(data)
            page_start += page_length

        return all_employees

    # --- END OF NEW FUNCTION ---

    async def check_connection(self) -> Dict[str, Any]:
        """
        Performs a simple API call to verify credentials and URL.
        """
        url = f"{self.base_url}/api/resource/ToDo?limit=1"
        headers = {"Authorization": self.auth_header}

        try:
            response = await self.client.get(url, headers=headers, timeout=10.0)
            response.raise_for_status()
            return {"status": "online", "details": "Successfully connected to ERPNext."}
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 403:
                return {
                    "status": "error",
                    "details": "Connection failed: Invalid API Key or Secret.",
                }
            return {
                "status": "error",
                "details": f"Connection failed with status {e.response.status_code}.",
            }
        except httpx.RequestError as e:
            return {"status": "offline", "details": f"Connection failed: {str(e)}"}
        except Exception as e:
            return {
                "status": "error",
                "details": f"An unexpected error occurred: {str(e)}",
            }
