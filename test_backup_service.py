"""Tests for database_backup_service — create, list, download helpers."""

import gzip
import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from services.database_backup_service import (
    BACKUP_DIR,
    create_backup_file,
    get_local_backup_path,
    list_local_backups,
)


# --------------- helpers ---------------

class _FakeQuery:
    """Mimics session.exec(select(Model)).all()"""
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class DummySession:
    """Bare-minimum session double that returns empty lists for every select."""

    def exec(self, _stmt):
        return _FakeQuery([])

    def commit(self):
        pass

    def refresh(self, _obj):
        pass


# --------------- create_backup_file ---------------

def test_create_backup_file_creates_gzip(tmp_path, monkeypatch):
    """create_backup_file should produce a valid .json.gz in BACKUP_DIR."""
    # Redirect BACKUP_DIR to tmp so we don't pollute the repo
    monkeypatch.setattr("services.database_backup_service.BACKUP_DIR", tmp_path)
    monkeypatch.setattr("services.database_backup_service.supabase_client", None)

    result = create_backup_file(DummySession())

    assert result["status"] == "success"
    assert result["filename"].endswith(".json.gz")
    assert result["size_bytes"] > 0

    # Verify we can decompress and parse
    path = tmp_path / result["filename"]
    assert path.exists()
    with gzip.open(path, "rt", encoding="utf-8") as fh:
        data = json.load(fh)
    assert data["version"] == "2.0"
    assert "products" in data
    assert "sales" in data
    assert "timestamp" in data


# --------------- list_local_backups ---------------

def test_list_local_backups_returns_sorted(tmp_path, monkeypatch):
    monkeypatch.setattr("services.database_backup_service.BACKUP_DIR", tmp_path)

    # Create two fake backup files with explicit mtimes
    f1 = tmp_path / "db_backup_20260101_000000.json.gz"
    f2 = tmp_path / "db_backup_20260102_000000.json.gz"
    f1.write_bytes(b"\x00" * 10)
    f2.write_bytes(b"\x00" * 20)
    # Force f2 to have a later mtime
    os.utime(f1, (1000000, 1000000))
    os.utime(f2, (2000000, 2000000))

    backups = list_local_backups()
    assert len(backups) == 2
    # Most recent first (by mtime — f2 has later mtime)
    assert backups[0]["filename"] == "db_backup_20260102_000000.json.gz"
    assert backups[0]["size_bytes"] == 20
    assert "modified_at" in backups[0]


def test_list_local_backups_empty(tmp_path, monkeypatch):
    monkeypatch.setattr("services.database_backup_service.BACKUP_DIR", tmp_path)
    assert list_local_backups() == []


# --------------- get_local_backup_path ---------------

def test_get_local_backup_path_rejects_missing_file(tmp_path, monkeypatch):
    monkeypatch.setattr("services.database_backup_service.BACKUP_DIR", tmp_path)

    with pytest.raises(HTTPException) as exc:
        get_local_backup_path("nonexistent.json.gz")
    assert exc.value.status_code == 404


def test_get_local_backup_path_rejects_non_gz(tmp_path, monkeypatch):
    monkeypatch.setattr("services.database_backup_service.BACKUP_DIR", tmp_path)
    (tmp_path / "evil.sh").write_text("#!/bin/bash\nrm -rf /")

    with pytest.raises(HTTPException) as exc:
        get_local_backup_path("evil.sh")
    assert exc.value.status_code == 404


def test_get_local_backup_path_prevents_traversal(tmp_path, monkeypatch):
    monkeypatch.setattr("services.database_backup_service.BACKUP_DIR", tmp_path)

    with pytest.raises(HTTPException) as exc:
        get_local_backup_path("../../etc/passwd")
    assert exc.value.status_code == 404


def test_get_local_backup_path_success(tmp_path, monkeypatch):
    monkeypatch.setattr("services.database_backup_service.BACKUP_DIR", tmp_path)
    target = tmp_path / "db_backup_20260101_120000.json.gz"
    target.write_bytes(b"\x00")

    result = get_local_backup_path("db_backup_20260101_120000.json.gz")
    assert result == target
