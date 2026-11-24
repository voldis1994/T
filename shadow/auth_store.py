"""Persist Capital.com credentials to .env so dashboard registration survives restart."""

from __future__ import annotations

from pathlib import Path

from shadow.config import ROOT

ENV_PATH = ROOT / ".env"

KEYS = (
    "CAPITAL_API_KEY",
    "CAPITAL_IDENTIFIER",
    "CAPITAL_PASSWORD",
    "CAPITAL_ENV",
    "SHADOW_EPIC",
    "SHADOW_SIZE",
    "SHADOW_HOST",
    "SHADOW_PORT",
)


def _parse_env(text: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for line in text.splitlines():
        raw = line.strip()
        if not raw or raw.startswith("#") or "=" not in raw:
            continue
        key, _, val = raw.partition("=")
        out[key.strip()] = val.strip().strip('"').strip("'")
    return out


def load_env_file(path: Path | None = None) -> dict[str, str]:
    p = path or ENV_PATH
    if not p.exists():
        return {}
    return _parse_env(p.read_text(encoding="utf-8"))


def save_credentials(
    *,
    api_key: str,
    identifier: str,
    password: str,
    env: str = "demo",
    epic: str | None = None,
    size: float | None = None,
    path: Path | None = None,
) -> Path:
    """Upsert Capital.com fields into .env (create from example if missing)."""
    p = path or ENV_PATH
    example = ROOT / ".env.example"
    if p.exists():
        current = load_env_file(p)
    elif example.exists():
        current = load_env_file(example)
    else:
        current = {}

    current["CAPITAL_API_KEY"] = api_key.strip()
    current["CAPITAL_IDENTIFIER"] = identifier.strip()
    current["CAPITAL_PASSWORD"] = password.strip()
    current["CAPITAL_ENV"] = (env or "demo").strip().lower()
    if epic:
        current["SHADOW_EPIC"] = epic.strip()
    if size is not None:
        current["SHADOW_SIZE"] = str(size)
    current.setdefault("SHADOW_HOST", "0.0.0.0")
    current.setdefault("SHADOW_PORT", "8080")

    lines = [
        "# SHADOW / Capital.com — saglabāts no dashboard reģistrācijas",
        f"CAPITAL_API_KEY={current['CAPITAL_API_KEY']}",
        f"CAPITAL_IDENTIFIER={current['CAPITAL_IDENTIFIER']}",
        f"CAPITAL_PASSWORD={current['CAPITAL_PASSWORD']}",
        f"CAPITAL_ENV={current['CAPITAL_ENV']}",
        "",
        f"SHADOW_EPIC={current.get('SHADOW_EPIC', 'EURUSD')}",
        f"SHADOW_SIZE={current.get('SHADOW_SIZE', '1000')}",
        "",
        f"SHADOW_HOST={current.get('SHADOW_HOST', '0.0.0.0')}",
        f"SHADOW_PORT={current.get('SHADOW_PORT', '8080')}",
        "",
    ]
    p.write_text("\n".join(lines), encoding="utf-8")
    return p


def mask_secret(value: str, keep: int = 4) -> str:
    if not value:
        return ""
    if len(value) <= keep:
        return "*" * len(value)
    return value[:keep] + "…" + ("*" * min(8, len(value) - keep))


def registration_status(settings) -> dict:
    registered = bool(settings.has_credentials)
    return {
        "registered": registered,
        "connected_env": settings.capital_env,
        "identifier_masked": mask_secret(settings.capital_identifier, 3)
        if registered
        else "",
        "api_key_masked": mask_secret(settings.capital_api_key, 4) if registered else "",
        "needs_registration": not registered,
    }