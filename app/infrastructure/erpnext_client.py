import time
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

    async def create_document(
        self, doctype: str, data: Dict[str, Any]
    ) -> httpx.Response:
        """
        Creates a new document in ERPNext.
        """
        url = f"{self.base_url}/api/resource/{doctype}"

        headers = {
            "Authorization": self.auth_header,
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

        # Use context manager to ensure proper cleanup
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(url, json=data, headers=headers)
            return response

    async def get_all_employees(
        self, force_refresh: bool = True
    ) -> List[Dict[str, Any]]:
        """
        Fetches all 'Active' employees from ERPNext.

        Handles pagination to retrieve the full list. Fetches:
        - name: ERPNext employee ID (HR-EMP-00001)
        - employee_name: Full name of the employee
        - employee_number: Company employee code (EHPL084, etc.)
        - company: Company name

        Args:
            force_refresh: If True, adds cache-busting parameter to force fresh data
        """
        all_employees = []
        page_start = 0
        page_length = 1000  # Fetch in batches of 1000

        # Cache-busting timestamp
        cache_buster = int(time.time() * 1000) if force_refresh else None

        print(f"\n{'=' * 80}")
        print(f"🔄 FETCHING EMPLOYEES FROM ERPNEXT")
        print(f"{'=' * 80}")
        print(f"Base URL: {self.base_url}")
        print(f"Force Refresh: {force_refresh}")
        if cache_buster:
            print(f"Cache Buster: {cache_buster}")

        # Use context manager for the HTTP client
        async with httpx.AsyncClient(timeout=60.0) as client:
            batch_num = 1
            while True:
                # Add cache buster to prevent stale data
                params = {
                    "fields": '["name", "employee_name", "employee_number", "company"]',
                    "filters": "[]",
                    "limit_page_length": page_length,
                    "limit_start": page_start,
                }

                if cache_buster:
                    params["_"] = cache_buster  # Cache-busting parameter

                url = f"{self.base_url}/api/resource/Employee"
                headers = {
                    "Authorization": self.auth_header,
                    "Accept": "application/json",
                    "Cache-Control": "no-cache, no-store, must-revalidate",  # Prevent caching
                    "Pragma": "no-cache",
                    "Expires": "0",
                }

                try:
                    print(
                        f"\n📦 Fetching batch {batch_num} (start: {page_start}, limit: {page_length})..."
                    )

                    response = await client.get(url, headers=headers, params=params)

                    # Better error handling
                    if response.status_code == 403:
                        raise Exception(
                            "ERPNext authentication failed. Check API credentials."
                        )
                    elif response.status_code == 404:
                        raise Exception(
                            "ERPNext Employee doctype not found or not accessible."
                        )

                    response.raise_for_status()

                    data = response.json().get("data", [])

                    if not data:
                        print(
                            f"   ✅ No more data in batch {batch_num}, pagination complete"
                        )
                        break  # No more data to fetch, exit the loop

                    print(f"   ✅ Received {len(data)} employees in batch {batch_num}")

                    # Show first employee from first batch for debugging
                    if batch_num == 1 and len(data) > 0:
                        print(f"\n📋 Sample employee from ERPNext:")
                        print(f"   Name (ID): {data[0].get('name')}")
                        print(f"   Employee Name: {data[0].get('employee_name')}")
                        print(f"   Employee Number: {data[0].get('employee_number')}")
                        print(f"   Company: {data[0].get('company')}")

                    all_employees.extend(data)
                    page_start += page_length
                    batch_num += 1

                except httpx.HTTPStatusError as e:
                    error_text = e.response.text if e.response else str(e)
                    print(f"\n❌ HTTP Error: {e.response.status_code}")
                    print(f"   Response: {error_text[:300]}")
                    raise Exception(
                        f"ERPNext API error ({e.response.status_code}): {error_text[:200]}"
                    )
                except httpx.RequestError as e:
                    print(f"\n❌ Network Error: {str(e)}")
                    raise Exception(f"Network error connecting to ERPNext: {str(e)}")

        print(f"\n{'=' * 80}")
        print(f"✅ TOTAL FETCHED: {len(all_employees)} active employees from ERPNext")
        print(f"{'=' * 80}\n")

        return all_employees

    async def check_connection(self) -> Dict[str, Any]:
        """
        Performs a simple API call to verify credentials and URL.
        """
        url = f"{self.base_url}/api/resource/ToDo?limit=1"
        headers = {
            "Authorization": self.auth_header,
            "Accept": "application/json",
            "Cache-Control": "no-cache",
        }

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(url, headers=headers)

                if response.status_code == 403:
                    return {
                        "status": "error",
                        "details": "Connection failed: Invalid API Key or Secret.",
                    }

                response.raise_for_status()
                return {
                    "status": "online",
                    "details": "Successfully connected to ERPNext.",
                }

        except httpx.HTTPStatusError as e:
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
