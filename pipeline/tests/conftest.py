import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

try:  # TEST_DATABASE_URL for the database tests, from the repo's .env
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parents[2] / ".env")
except ImportError:
    pass

from footstats import FootStats  # noqa: E402


@pytest.fixture(scope="session")
def fs() -> FootStats:
    return FootStats()


@pytest.fixture(scope="session")
def client(fs):
    from fastapi.testclient import TestClient

    import app as app_module

    app_module.get_stats.cache_clear()
    app_module.app.dependency_overrides[app_module.get_stats] = lambda: fs
    with TestClient(app_module.app) as c:
        yield c
