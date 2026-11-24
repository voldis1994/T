"""Load configuration from YAML + environment."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    capital_api_key: str = ""
    capital_identifier: str = ""
    capital_password: str = ""
    capital_env: str = "demo"
    shadow_epic: str = "EURUSD"
    shadow_size: float = 1000
    shadow_host: str = "0.0.0.0"
    shadow_port: int = 8080

    @property
    def capital_base_url(self) -> str:
        if self.capital_env.lower() == "live":
            return "https://api-capital.backend-capital.com"
        return "https://demo-api-capital.backend-capital.com"

    @staticmethod
    def _is_placeholder(value: str) -> bool:
        v = (value or "").strip().lower()
        if not v:
            return True
        placeholders = (
            "your_api_key_here",
            "your_email@example.com",
            "your_api_key_password",
            "changeme",
            "xxx",
            "todo",
            "example",
        )
        return v in placeholders or v.startswith("your_")

    @property
    def has_credentials(self) -> bool:
        """True only when real (non-placeholder) API credentials are set."""
        if self._is_placeholder(self.capital_api_key):
            return False
        if self._is_placeholder(self.capital_identifier):
            return False
        if self._is_placeholder(self.capital_password):
            return False
        return True


def load_yaml_config(path: Path | None = None) -> dict[str, Any]:
    cfg_path = path or (ROOT / "config.yaml")
    with open(cfg_path, encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    settings = Settings()
    if settings.shadow_epic:
        data.setdefault("instrument", {})["epic"] = settings.shadow_epic
    if settings.shadow_size:
        data.setdefault("risk", {})["default_size"] = settings.shadow_size
    data["_settings"] = settings
    return data


settings = Settings()
config = load_yaml_config()


class AppState(BaseModel):
    """Shared runtime state pushed to the dashboard."""

    mode: str = "idle"  # idle | waiting_handover | active | paper | analysis_only | error
    connected: bool = False
    paper: bool = True
    # capital = īsti Capital.com orderi | paper = simulācija | none = tikai analīze
    broker: str = "none"
    trading_enabled: bool = False
    allow_paper_trading: bool = False
    epic: str = "EURUSD"
    last_price: float | None = None
    bid: float | None = None
    ask: float | None = None
    spread: float | None = None
    regime: str = "UNKNOWN"
    structure: str = "UNKNOWN"
    signal: str = "HOLD"
    confluence: float = 0.0
    account_balance: float | None = None
    account_available: float | None = None
    account_pnl: float | None = None
    open_positions: list[dict[str, Any]] = Field(default_factory=list)
    zones: list[dict[str, Any]] = Field(default_factory=list)
    last_decision: dict[str, Any] = Field(default_factory=dict)
    decisions: list[dict[str, Any]] = Field(default_factory=list)
    trades: list[dict[str, Any]] = Field(default_factory=list)
    candles: list[dict[str, Any]] = Field(default_factory=list)
    indicators: dict[str, Any] = Field(default_factory=dict)
    peers: dict[str, Any] = Field(default_factory=dict)
    news_risk: str = "ok"
    session: str = "off"
    message: str = "Gaida startu"
    error: str | None = None
    stats: dict[str, Any] = Field(default_factory=dict)
    handover_detected_at: str | None = None
    started_at: str | None = None


state = AppState()