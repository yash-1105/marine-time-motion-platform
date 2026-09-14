import pytest
from fastapi.testclient import TestClient
from apps.api.main import app
from apps.api.core.database import get_db

@pytest.fixture
def client():
    # Similar to other tests, we will mock the auth dependency
    pass

# We can just write a test for load synthetic dataset.
