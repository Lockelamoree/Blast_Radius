from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from blast_radius.config import Settings
from blast_radius.main import create_app


@pytest.fixture
def test_settings(tmp_path: Path) -> Settings:
    package_dir = Path(__file__).resolve().parents[1] / "blast_radius"
    return Settings(
        base_dir=package_dir,
        database_path=tmp_path / "test.db",
        openai_api_key=None,
        live_generation=False,
        session_ttl_minutes=180,
    )


@pytest.fixture
def client(test_settings: Settings) -> TestClient:
    with TestClient(create_app(test_settings)) as test_client:
        yield test_client

