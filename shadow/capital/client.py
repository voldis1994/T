"""Capital.com REST API client.

Auth: POST /session with X-CAP-API-KEY → CST + X-SECURITY-TOKEN headers.
Session idle timeout ≈ 10 minutes — auto-refresh on 401.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx

logger = logging.getLogger("shadow.capital")


class CapitalClient:
    def __init__(
        self,
        api_key: str,
        identifier: str,
        password: str,
        base_url: str,
        *,
        timeout: float = 30.0,
    ) -> None:
        self.api_key = api_key
        self.identifier = identifier
        self.password = password
        self.base_url = base_url.rstrip("/")
        self.cst: str | None = None
        self.security_token: str | None = None
        self._client = httpx.AsyncClient(timeout=timeout)
        self._lock = asyncio.Lock()

    @property
    def authenticated(self) -> bool:
        return bool(self.cst and self.security_token)

    def _auth_headers(self) -> dict[str, str]:
        h = {
            "Content-Type": "application/json",
            "X-CAP-API-KEY": self.api_key,
        }
        if self.cst:
            h["CST"] = self.cst
        if self.security_token:
            h["X-SECURITY-TOKEN"] = self.security_token
        return h

    async def login(self) -> dict[str, Any]:
        async with self._lock:
            url = f"{self.base_url}/api/v1/session"
            r = await self._client.post(
                url,
                headers={"Content-Type": "application/json", "X-CAP-API-KEY": self.api_key},
                json={
                    "identifier": self.identifier,
                    "password": self.password,
                    "encryptedPassword": False,
                },
            )
            r.raise_for_status()
            self.cst = r.headers.get("CST")
            self.security_token = r.headers.get("X-SECURITY-TOKEN")
            data = r.json()
            logger.info("Capital.com session opened (env=%s)", self.base_url)
            return data

    async def logout(self) -> None:
        if not self.authenticated:
            return
        try:
            await self._client.delete(f"{self.base_url}/api/v1/session", headers=self._auth_headers())
        except Exception as exc:  # noqa: BLE001
            logger.warning("logout: %s", exc)
        finally:
            self.cst = None
            self.security_token = None

    async def close(self) -> None:
        await self.logout()
        await self._client.aclose()

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json: dict | None = None,
        params: dict | None = None,
        retry_auth: bool = True,
    ) -> Any:
        if not self.authenticated:
            await self.login()
        url = f"{self.base_url}{path}"
        r = await self._client.request(
            method, url, headers=self._auth_headers(), json=json, params=params
        )
        if r.status_code in (401, 403) and retry_auth:
            await self.login()
            r = await self._client.request(
                method, url, headers=self._auth_headers(), json=json, params=params
            )
        if r.status_code >= 400:
            logger.error("API %s %s → %s %s", method, path, r.status_code, r.text[:500])
            r.raise_for_status()
        if r.status_code == 204 or not r.content:
            return {}
        return r.json()

    # ── Market data ──────────────────────────────────────────────

    async def get_prices(
        self,
        epic: str,
        resolution: str = "MINUTE",
        max_bars: int = 300,
    ) -> list[dict[str, Any]]:
        data = await self._request(
            "GET",
            f"/api/v1/prices/{epic}",
            params={"resolution": resolution, "max": max_bars},
        )
        return data.get("prices", [])

    async def get_market(self, epic: str) -> dict[str, Any]:
        return await self._request("GET", f"/api/v1/markets/{epic}")

    async def search_markets(self, search_term: str) -> dict[str, Any]:
        return await self._request("GET", "/api/v1/markets", params={"searchTerm": search_term})

    async def get_client_sentiment(self, market_id: str) -> dict[str, Any]:
        return await self._request("GET", f"/api/v1/clientsentiment/{market_id}")

    # ── Account ──────────────────────────────────────────────────

    async def get_accounts(self) -> dict[str, Any]:
        return await self._request("GET", "/api/v1/accounts")

    async def switch_account(self, account_id: str) -> dict[str, Any]:
        return await self._request("PUT", "/api/v1/session", json={"accountId": account_id})

    # ── Positions ────────────────────────────────────────────────

    async def get_positions(self) -> list[dict[str, Any]]:
        data = await self._request("GET", "/api/v1/positions")
        return data.get("positions", [])

    async def get_position(self, deal_id: str) -> dict[str, Any]:
        return await self._request("GET", f"/api/v1/positions/{deal_id}")

    async def open_position(
        self,
        epic: str,
        direction: str,
        size: float,
        *,
        stop_level: float | None = None,
        profit_level: float | None = None,
        stop_distance: float | None = None,
        profit_distance: float | None = None,
        guaranteed_stop: bool = False,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {
            "epic": epic,
            "direction": direction.upper(),
            "size": size,
        }
        if stop_level is not None:
            body["stopLevel"] = stop_level
        if profit_level is not None:
            body["profitLevel"] = profit_level
        if stop_distance is not None:
            body["stopDistance"] = stop_distance
        if profit_distance is not None:
            body["profitDistance"] = profit_distance
        if guaranteed_stop:
            body["guaranteedStop"] = True
        return await self._request("POST", "/api/v1/positions", json=body)

    async def update_position(
        self,
        deal_id: str,
        *,
        stop_level: float | None = None,
        profit_level: float | None = None,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {}
        if stop_level is not None:
            body["stopLevel"] = stop_level
        if profit_level is not None:
            body["profitLevel"] = profit_level
        return await self._request("PUT", f"/api/v1/positions/{deal_id}", json=body)

    async def close_position(self, deal_id: str) -> dict[str, Any]:
        return await self._request("DELETE", f"/api/v1/positions/{deal_id}")

    async def confirm(self, deal_reference: str) -> dict[str, Any]:
        return await self._request("GET", f"/api/v1/confirms/{deal_reference}")

    async def get_working_orders(self) -> list[dict[str, Any]]:
        data = await self._request("GET", "/api/v1/workingorders")
        return data.get("workingOrders", [])

    async def create_working_order(
        self,
        epic: str,
        direction: str,
        size: float,
        level: float,
        order_type: str = "LIMIT",
        *,
        stop_distance: float | None = None,
        profit_distance: float | None = None,
        time_in_force: str = "GOOD_TILL_CANCELLED",
    ) -> dict[str, Any]:
        body: dict[str, Any] = {
            "epic": epic,
            "direction": direction.upper(),
            "size": size,
            "level": level,
            "type": order_type.upper(),
            "timeInForce": time_in_force,
        }
        if stop_distance is not None:
            body["stopDistance"] = stop_distance
        if profit_distance is not None:
            body["profitDistance"] = profit_distance
        return await self._request("POST", "/api/v1/workingorders", json=body)