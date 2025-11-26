# Iridium-main/app/infrastructure/erpnext_client.py

from typing import Any, Dict

import httpx

class ERPNextClient:
    """
    A client for making authenticated API requests to an ERPNext instance.
    """

    def __init__(self, base_url: str, api_key: str, api_secret: str):
        # Ensure the base URL is clean and doesn't have a trailing slash
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.api_secret = api_secret
        self.auth_header = f"token {self.api_key}:{self.api_secret}"

    async def create_document(
        self, doctype: str, data: Dict[str, Any]
    ) -> httpx.Response:
        """
        Creates a new document in ERPNext.

        Args:
            doctype: The name of the Doctype to create (e.g., "Sales Invoice").
            data: A dictionary representing the document to be created.

        Returns:
            The httpx.Response object from the API call.
        """
        # The data for a new document is sent inside a 'data' key.
        payload = {"data": data}

        # Construct the full URL for the API endpoint
        url = f"{self.base_url}/api/resource/{doctype}"

        headers = {
            "Authorization": self.auth_header,
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

        # Use an async client to make the request
        async with httpx.AsyncClient() as client:
            # A generous timeout is good for external API calls
            response = await client.post(
                url, json=payload, headers=headers, timeout=30.0
            )

        return response

    async def check_connection(self) -> Dict[str, Any]:
        """
        Performs a simple API call to verify that the credentials and URL are valid.
        It tries to fetch the list of ToDo items, limited to 1.
        """
        url = f"{self.base_url}/api/resource/ToDo?limit=1"
        headers = {"Authorization": self.auth_header}

        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(url, headers=headers, timeout=10.0)

            # Raise an exception for 4xx or 5xx status codes
            response.raise_for_status()

            # If we reach here, the connection is successful
            return {"status": "online", "details": "Successfully connected to ERPNext."}

        except httpx.HTTPStatusError as e:
            # Handle specific HTTP errors (like 401 Unauthorized, 403 Forbidden, 404 Not Found)
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
            # Handle network errors (like DNS failure, connection refused)
            return {"status": "offline", "details": f"Connection failed: {str(e)}"}
        except Exception as e:
            # Catch any other unexpected errors
            return {
                "status": "error",
                "details": f"An unexpected error occurred: {str(e)}",
            }
            # Catch any other unexpected errors
            return {"status": "error", "details": f"An unexpected error occurred: {str(e)}"}
