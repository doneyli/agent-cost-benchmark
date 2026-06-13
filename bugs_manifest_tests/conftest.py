"""Shared fixtures for manifest tests."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from target_project.app import app
from target_project.models import init_db


@pytest.fixture(autouse=True)
def setup_db(tmp_path, monkeypatch):
    import target_project.models as models
    monkeypatch.setattr(models, "DB_PATH", tmp_path / "test.db")
    init_db()


@pytest.fixture
def client():
    return TestClient(app)
