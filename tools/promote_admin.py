"""Promote an existing account using DATABASE_URL; run with authorized DB access."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sqlalchemy import update
from server.database import get_db, users, now

parser = argparse.ArgumentParser(description="Promote an existing MuaSamCong Pro account to admin")
parser.add_argument("email", help="Email of the existing account")
args = parser.parse_args()
with get_db().engine.begin() as conn:
    result = conn.execute(update(users).where(users.c.email == args.email.strip().lower())
                          .values(role="admin", updated_at=now()))
if result.rowcount != 1:
    raise SystemExit("No matching account; register first, then rerun this command.")
print("Admin role updated.")
