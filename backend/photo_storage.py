"""Photo storage behind one small interface, so the backend can move from MongoDB to S3 / Cloudflare R2 later.

Every photo goes through `prepare_image` first (EXIF-rotated, RGB, longest side ≤ 1200 px, JPEG), so whichever
store is active only ever holds small, display-ready files. A stored photo is identified by an opaque `path`
string that starts with the store's scheme (e.g. "mongo:<id>", later "s3:<key>"), which is what the
local_accounts documents keep in `photo_path`.

To add S3/R2: implement `PhotoStore` with boto3 (put_object / get_object), give it scheme "s3", and return it
from `make_store()` based on an env var. Existing "mongo:" paths keep resolving through the Mongo store.
"""

import io
import uuid
from datetime import datetime, timezone
from typing import Protocol

from motor.motor_asyncio import AsyncIOMotorDatabase
from PIL import Image, ImageOps

MAX_SIDE = 1200
JPEG_QUALITY = 82


class PhotoStore(Protocol):
    scheme: str

    async def put(self, data: bytes, content_type: str) -> str:
        """Save the bytes and return an opaque path beginning with `scheme:`."""

    async def get(self, path: str) -> tuple[bytes, str]:
        """Return (bytes, content_type). Raise KeyError if the path is unknown."""

    async def delete(self, path: str) -> None:
        """Remove a stored photo. Never raises for a path that is already gone."""


def prepare_image(data: bytes) -> tuple[bytes, str]:
    """Normalise an upload: honour EXIF rotation, flatten to RGB, cap at 1200 px, compress to JPEG."""
    img = Image.open(io.BytesIO(data))
    img = ImageOps.exif_transpose(img)
    if img.mode not in ("RGB", "L"):
        img = img.convert("RGB")
    img.thumbnail((MAX_SIDE, MAX_SIDE), Image.LANCZOS)
    out = io.BytesIO()
    img.save(out, format="JPEG", quality=JPEG_QUALITY, optimize=True, progressive=True)
    return out.getvalue(), "image/jpeg"


class MongoPhotoStore:
    """Photos as documents in the `photos` collection (each ≤ ~300 KB after prepare_image, far under Mongo's 16 MB)."""

    scheme = "mongo"

    def __init__(self, db: AsyncIOMotorDatabase):
        self.col = db.photos

    async def put(self, data: bytes, content_type: str) -> str:
        pid = uuid.uuid4().hex
        await self.col.insert_one({"id": pid, "data": data, "content_type": content_type, "size": len(data), "created_at": datetime.now(timezone.utc)})
        return f"{self.scheme}:{pid}"

    async def get(self, path: str) -> tuple[bytes, str]:
        scheme, _, pid = path.partition(":")
        doc = await self.col.find_one({"id": pid}, {"_id": 0, "data": 1, "content_type": 1}) if scheme == self.scheme else None
        if not doc:
            raise KeyError(path)
        return bytes(doc["data"]), doc["content_type"]

    async def delete(self, path: str) -> None:
        scheme, _, pid = path.partition(":")
        if scheme == self.scheme and pid:
            await self.col.delete_one({"id": pid})


def make_store(db: AsyncIOMotorDatabase) -> PhotoStore:
    """Single place to choose the backend. Swap on an env var when S3/R2 arrives."""
    return MongoPhotoStore(db)
