"""Emergent Object Storage: the app never talks to storage directly, only this backend does."""

import asyncio
import logging
import os

import httpx

STORAGE_BASE = (os.environ.get("INTEGRATION_PROXY_URL") or "").strip() or "https://integrations.emergentagent.com"
STORAGE_URL = STORAGE_BASE.rstrip("/") + "/objstore/api/v1/storage"
APP_NAME = "nvm"

logger = logging.getLogger(__name__)
_storage_key: str | None = None
_lock = asyncio.Lock()


async def init_storage(emergent_key: str) -> str:
    """Idempotent handshake: one storage_key per emergent key, reused for every call."""
    global _storage_key
    if _storage_key:
        return _storage_key
    async with _lock:
        if _storage_key:
            return _storage_key
        async with httpx.AsyncClient(timeout=30) as c:
            r = await c.post(f"{STORAGE_URL}/init", json={"emergent_key": emergent_key})
            r.raise_for_status()
            _storage_key = r.json()["storage_key"]
    return _storage_key


def object_path(kind: str, name: str) -> str:
    return f"{APP_NAME}/{kind}/{name}"


async def put_object(emergent_key: str, path: str, data: bytes, content_type: str) -> dict:
    key = await init_storage(emergent_key)
    async with httpx.AsyncClient(timeout=120) as c:
        r = await c.put(f"{STORAGE_URL}/objects/{path}", headers={"X-Storage-Key": key, "Content-Type": content_type}, content=data)
    if r.status_code == 503:  # stale key: reset and retry once
        global _storage_key
        _storage_key = None
        key = await init_storage(emergent_key)
        async with httpx.AsyncClient(timeout=120) as c:
            r = await c.put(f"{STORAGE_URL}/objects/{path}", headers={"X-Storage-Key": key, "Content-Type": content_type}, content=data)
    r.raise_for_status()
    return r.json()


async def get_object(emergent_key: str, path: str) -> tuple[bytes, str]:
    key = await init_storage(emergent_key)
    async with httpx.AsyncClient(timeout=60) as c:
        r = await c.get(f"{STORAGE_URL}/objects/{path}", headers={"X-Storage-Key": key})
    r.raise_for_status()
    return r.content, r.headers.get("Content-Type", "application/octet-stream")
