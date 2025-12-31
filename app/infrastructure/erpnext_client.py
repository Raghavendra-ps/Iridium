# Iridium-main/app/infrastructure/erpnext_client.py

from typing import Any, Dict

import httpx


class ERPNextClient:
    """A client for making authenticated API requests to an ERPNext instance."""

    def __init__(self, base_url: str, api_key: str, api_secret: str):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.api_secret = api_secret
        self.auth_header = f"token {self.api_key}:{self.api_secret}"
        # --- START OF FINAL 417 FIX ---
        # Initialize a persistent client that is configured to only use HTTP/1.1
        self.client = httpx.AsyncClient(http1=True, http2=False)
        # --- END OF FINAL 417 FIX ---

    async def create_document(
        self, doctype: str, data: Dict[str, Any]
    ) -> httpx.Response:
        """Creates a new document in ERPNext."""
        payload = data
        url = f"{self.base_url}/api/resource/{doctype}"

        headers = {
            "Authorization": self.auth_header,
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

        # Use the pre-configured client instance
        response = await self.client.post(
            url, json=payload, headers=headers, timeout=30.0
        )
        return response

    async def check_connection(self) -> Dict[str, Any]:
        """Performs a simple API call to verify credentials and URL."""
        url = f"{self.base_url}/api/resource/ToDo?limit=1"
        headers = {"Authorization": self.auth_header}

        try:
            # Use the pre-configured client instance
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
