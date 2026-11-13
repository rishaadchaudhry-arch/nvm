"""Where the tests find the running backend and the admin login.

Everything comes from the environment (or backend/.env), so no password is ever written down in a
test file — these tests used to carry a real admin password in plain text, in a public repository.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

BASE_URL = (os.environ.get("EXPO_PUBLIC_BACKEND_URL") or "http://localhost:8001").rstrip("/")
ADMIN_EMAIL = (os.environ.get("ADMIN_EMAIL") or "").strip().lower()
ADMIN_PW = os.environ.get("ADMIN_PASSWORD") or ""

if not ADMIN_EMAIL or not ADMIN_PW:
    raise RuntimeError("ADMIN_EMAIL and ADMIN_PASSWORD must be set (see backend/.env.example) before running the tests.")
