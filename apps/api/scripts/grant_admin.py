"""Grant (or revoke) platform-admin status for a user by email.

No API endpoint does this — see app/api/deps.py's require_platform_admin
docstring. This script, run with direct access to the deployment's
database connection, is the only way to create the first platform admin.
That's deliberate: there is no self-service or API-driven privilege
escalation path to platform admin, matching the brief's "tightly
restricted" requirement for admin capability.

Usage (run from apps/api, with the venv active and DATABASE_URL pointed
at the target environment):
    python scripts/grant_admin.py user@example.com
    python scripts/grant_admin.py user@example.com --revoke
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select  # noqa: E402

from app.db.session import AsyncSessionLocal  # noqa: E402
from app.models.user import User  # noqa: E402


async def main(email: str, revoke: bool) -> None:
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(User).where(User.email == email))
        user = result.scalar_one_or_none()
        if user is None:
            print(f"No user found with email: {email}")
            return

        user.is_platform_admin = not revoke
        await db.commit()
        action = "revoked from" if revoke else "granted to"
        print(f"Platform admin {action} {email}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("email")
    parser.add_argument("--revoke", action="store_true", help="Remove platform-admin status instead of granting it")
    args = parser.parse_args()
    asyncio.run(main(args.email, args.revoke))
