from pathlib import Path

from shadow.auth_store import load_env_file, mask_secret, registration_status, save_credentials
from shadow.config import Settings


def test_placeholder_credentials():
    s = Settings(
        capital_api_key="your_api_key_here",
        capital_identifier="your_email@example.com",
        capital_password="your_api_key_password",
    )
    assert s.has_credentials is False


def test_real_credentials_flag():
    s = Settings(
        capital_api_key="abc123XYZ",
        capital_identifier="trader@mail.lv",
        capital_password="secret-pass-99",
    )
    assert s.has_credentials is True


def test_save_and_load_env(tmp_path: Path):
    env = tmp_path / ".env"
    save_credentials(
        api_key="KEY123456",
        identifier="me@mail.lv",
        password="pass-xyz",
        env="demo",
        epic="EURUSD",
        size=500,
        path=env,
    )
    data = load_env_file(env)
    assert data["CAPITAL_API_KEY"] == "KEY123456"
    assert data["CAPITAL_IDENTIFIER"] == "me@mail.lv"
    assert data["SHADOW_SIZE"] == "500"


def test_mask_and_status():
    assert "…" in mask_secret("abcdefghij")
    s = Settings(
        capital_api_key="KEY123456",
        capital_identifier="me@mail.lv",
        capital_password="pass-xyz",
        capital_env="demo",
    )
    st = registration_status(s)
    assert st["registered"] is True
    assert st["needs_registration"] is False
