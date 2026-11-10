# Lists (and with --delete removes) TEST_ traditions created in the last N minutes by this test run
import asyncio
import os
import sys
from datetime import datetime, timedelta, timezone

from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

load_dotenv("/app/backend/.env")


async def main():
    mins = int(sys.argv[1]) if len(sys.argv) > 1 else 10
    db = AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
    since = datetime.now(timezone.utc) - timedelta(minutes=mins)
    docs = await db.traditions.find({"title": {"$regex": "^TEST_"}}, {"_id": 0, "id": 1, "title": 1, "created_at": 1}).to_list(100)
    recent = [d for d in docs if d.get("created_at") and (d["created_at"].replace(tzinfo=timezone.utc) if d["created_at"].tzinfo is None else d["created_at"]) >= since]
    print("all TEST_:", len(docs), "recent:", [(d["id"], d["title"], d["created_at"]) for d in recent])
    if "--delete" in sys.argv:
        for d in recent:
            await db.traditions.delete_one({"id": d["id"]})
        print("deleted", len(recent))
    la = await db.local_accounts.find({}, {"_id": 0, "id": 1, "body": 1, "deleted": 1, "place_key": 1}).to_list(100)
    print("local_accounts:", [(x["id"][:8], x["place_key"], x["deleted"], x["body"][:30]) for x in la])


asyncio.run(main())
