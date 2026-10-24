"""
Food Freshness Monitoring Platform - Streamlit Backend API Client
Connects the Streamlit UI to the FastAPI REST endpoints.
"""
from typing import Dict, Any, Optional, List
import httpx
from streamlit_app.config import config


class ApiException(Exception):
    def __init__(self, message: str, status_code: Optional[int] = None, detail: Any = None):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.detail = detail


class StreamlitApiClient:
    def __init__(self):
        self.base_url = config.API_BASE_URL.rstrip("/")
        self.timeout = config.API_TIMEOUT_SECONDS

    def _headers(self, token: Optional[str] = None) -> Dict[str, str]:
        headers = {"Accept": "application/json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        return headers

    def _request(self, method: str, endpoint: str, token: Optional[str] = None, **kwargs) -> Any:
        url = f"{self.base_url}/{endpoint.lstrip('/')}"
        headers = self._headers(token)
        if "headers" in kwargs:
            headers.update(kwargs.pop("headers"))

        try:
            with httpx.Client(timeout=self.timeout) as client:
                res = client.request(method, url, headers=headers, **kwargs)
                if res.status_code >= 400:
                    try:
                        err_json = res.json()
                        detail = err_json.get("detail", res.text)
                    except Exception:
                        detail = res.text
                    raise ApiException(
                        message=str(detail) if isinstance(detail, str) else "API Request Error",
                        status_code=res.status_code,
                        detail=detail,
                    )
                return res.json()
        except httpx.RequestError as exc:
            raise ApiException(f"Could not connect to FastAPI backend at {self.base_url}: {str(exc)}")

    # --------------------------------------------------------------------------
    # Auth
    # --------------------------------------------------------------------------
    def login(self, email: str, password: str) -> Dict[str, Any]:
        return self._request("POST", "auth/login", json={"email": email, "password": password})

    def register(self, data: Dict[str, Any]) -> Dict[str, Any]:
        return self._request("POST", "auth/register", json=data)

    def me(self, token: str) -> Dict[str, Any]:
        return self._request("GET", "auth/me", token=token)

    # --------------------------------------------------------------------------
    # Inventory
    # --------------------------------------------------------------------------
    def get_inventory(self, token: str, params: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        return self._request("GET", "inventory", token=token, params=params or {})

    def create_inventory_item(self, token: str, data: Dict[str, Any]) -> Dict[str, Any]:
        return self._request("POST", "inventory", token=token, json=data)

    def seed_dataset(self, token: str) -> Dict[str, Any]:
        return self._request("POST", "inventory/seed-dataset", token=token)

    # --------------------------------------------------------------------------
    # Dashboard & Analytics
    # --------------------------------------------------------------------------
    def get_dashboard_stats(self, token: str) -> Dict[str, Any]:
        return self._request("GET", "dashboard/stats", token=token)

    def get_reports_summary(self, token: str) -> Dict[str, Any]:
        return self._request("GET", "reports/summary", token=token)

    def get_retailer_inventory(self, token: str, params: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        return self._request("GET", "retailer/inventory", token=token, params=params or {})

    def get_retailer_analytics(self, token: str) -> Dict[str, Any]:
        return self._request("GET", "retailer/analytics", token=token)

    def get_inspector_dashboard(self, token: str) -> Dict[str, Any]:
        return self._request("GET", "inspector/dashboard", token=token)

    def get_warehouse_zones(self, token: str) -> List[Dict[str, Any]]:
        return self._request("GET", "warehouse/zones", token=token)

    def get_admin_kpis(self, token: str) -> Dict[str, Any]:
        return self._request("GET", "admin/metrics/overview", token=token)

    def get_admin_users(self, token: str) -> List[Dict[str, Any]]:
        return self._request("GET", "admin/users", token=token)


api_client = StreamlitApiClient()
