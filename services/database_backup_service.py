from __future__ import annotations

import gzip
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import HTTPException
from sqlmodel import Session, select

from database.models import Client, Payment, Product, Sale, SaleItem, Settings, User
from database.session import supabase_client

BACKUP_DIR = Path("backups")
BACKUP_DIR.mkdir(parents=True, exist_ok=True)


def _now_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _serialize_snapshot(session: Session) -> dict[str, Any]:
    data: dict[str, Any] = {
        "version": "2.0",
        "timestamp": _now_utc_iso(),
        "products": [p.model_dump() for p in session.exec(select(Product)).all()],
        "clients": [c.model_dump() for c in session.exec(select(Client)).all()],
        "users": [u.model_dump() for u in session.exec(select(User)).all()],
        "settings": [s.model_dump() for s in session.exec(select(Settings)).all()],
        "sales": [],
        "sale_items": [i.model_dump() for i in session.exec(select(SaleItem)).all()],
        "payments": [],
    }

    for s in session.exec(select(Sale)).all():
        row = s.model_dump()
        if s.timestamp:
            row["timestamp"] = s.timestamp.isoformat()
        data["sales"].append(row)

    for p in session.exec(select(Payment)).all():
        row = p.model_dump()
        if p.date:
            row["date"] = p.date.isoformat()
        data["payments"].append(row)

    return data


def _backup_filename() -> str:
    return f"db_backup_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.json.gz"


def create_backup_file(session: Session) -> dict[str, Any]:
    snapshot = _serialize_snapshot(session)
    filename = _backup_filename()
    path = BACKUP_DIR / filename

    with gzip.open(path, "wt", encoding="utf-8") as fh:
        json.dump(snapshot, fh, ensure_ascii=False)

    result = {
        "status": "success",
        "filename": filename,
        "path": str(path),
        "timestamp": snapshot["timestamp"],
        "size_bytes": path.stat().st_size,
    }

    bucket_name = os.getenv("SUPABASE_BACKUP_BUCKET")
    if bucket_name and supabase_client:
        try:
            with path.open("rb") as fh:
                remote_name = f"db/{filename}"
                supabase_client.storage.from_(bucket_name).upload(
                    path=remote_name,
                    file=fh,
                    file_options={"content-type": "application/gzip", "upsert": "false"},
                )
            result["supabase"] = {"uploaded": True, "bucket": bucket_name, "object": remote_name}
        except Exception as exc:
            result["supabase"] = {"uploaded": False, "error": str(exc)}

    return result


def list_local_backups() -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for p in sorted(BACKUP_DIR.glob("db_backup_*.json.gz"), key=lambda item: item.stat().st_mtime, reverse=True):
        st = p.stat()
        entries.append(
            {
                "filename": p.name,
                "size_bytes": st.st_size,
                "modified_at": datetime.fromtimestamp(st.st_mtime, tz=timezone.utc).isoformat(),
            }
        )
    return entries


def get_local_backup_path(filename: str) -> Path:
    safe_name = os.path.basename(filename)
    path = BACKUP_DIR / safe_name
    if not path.exists() or path.suffix != ".gz":
        raise HTTPException(status_code=404, detail="Backup file not found")
    return path
