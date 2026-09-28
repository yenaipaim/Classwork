"""REST client for calling the Go pet hospital API."""

from __future__ import annotations

import logging
from typing import Any

import httpx

from .config import Config
from .errors import (
    BackendAPIError,
    BackendInvalidResponseError,
    BackendTimeoutError,
    BackendUnavailableError,
)

logger = logging.getLogger(__name__)


class PetHospitalClient:
    """HTTP client for the Go pet hospital REST API."""

    def __init__(self, config: Config) -> None:
        self._base_url = config.pet_hospital_base_url.rstrip("/")
        self._timeout = config.http_timeout
        self._max_retries = config.max_retries

    async def _request(
        self,
        method: str,
        path: str,
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
    ) -> Any:
        """Generic HTTP request with retries and error handling."""
        url = f"{self._base_url}{path}"
        last_exception: Exception | None = None

        for attempt in range(self._max_retries + 1):
            try:
                async with httpx.AsyncClient(timeout=self._timeout) as client:
                    response = await client.request(
                        method, url, params=params, json=json_body
                    )

                    if response.status_code >= 500:
                        raise BackendAPIError(
                            message=f"Backend returned HTTP {response.status_code}",
                            status_code=response.status_code,
                        )
                    if response.status_code >= 400:
                        raise BackendAPIError(
                            message=f"Backend returned HTTP {response.status_code}: {response.text}",
                            status_code=response.status_code,
                        )

                    # Some endpoints (DELETE) may return 204 or no body
                    if response.status_code == 204 or not response.text.strip():
                        return {"code": 200, "message": "ok", "data": None}

                    data = response.json()
                    if not isinstance(data, dict):
                        raise BackendInvalidResponseError("Response is not a JSON object")

                    if data.get("code") != 200:
                        raise BackendAPIError(
                            message=data.get("message", "Unknown backend error"),
                            details={"backend_response": data},
                        )

                    return data.get("data")

            except httpx.TimeoutException as e:
                last_exception = e
                if attempt < self._max_retries:
                    logger.warning(f"Timeout, retrying ({attempt+1}/{self._max_retries})")
                    continue
                raise BackendTimeoutError(f"Timeout after {self._max_retries+1} attempts")

            except httpx.ConnectError as e:
                last_exception = e
                if attempt < self._max_retries:
                    logger.warning(f"Connect error, retrying ({attempt+1}/{self._max_retries})")
                    continue
                raise BackendUnavailableError(f"Cannot connect to {self._base_url}")

            except (BackendAPIError, BackendInvalidResponseError):
                raise

            except Exception as e:
                raise BackendInvalidResponseError(f"Unexpected error: {e}")

        if last_exception:
            raise BackendUnavailableError(f"Failed: {last_exception}")
        raise BackendUnavailableError("Failed to connect")

    async def get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        return await self._request("GET", path, params=params)

    async def post(self, path: str, json_body: dict[str, Any] | None = None) -> Any:
        return await self._request("POST", path, json_body=json_body)

    async def put(self, path: str, json_body: dict[str, Any] | None = None) -> Any:
        return await self._request("PUT", path, json_body=json_body)

    async def patch(self, path: str, json_body: dict[str, Any] | None = None) -> Any:
        return await self._request("PATCH", path, json_body=json_body)

    async def delete(self, path: str) -> Any:
        return await self._request("DELETE", path)

    # Backward compat
    async def get_pets(self, params: dict[str, Any]) -> dict[str, Any]:
        return await self.get("/api/v1/pets", params=params)

    async def health_check(self) -> dict[str, Any]:
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(f"{self._base_url}/health")
                response.raise_for_status()
                return response.json()
        except Exception as e:
            raise BackendUnavailableError(f"Health check failed: {e}")
