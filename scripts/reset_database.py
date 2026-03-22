from __future__ import annotations

import argparse
import asyncio
import os
from pathlib import Path

from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient


ROOT = Path(__file__).resolve().parents[1]
REQUIRED_CONFIRMATION = "RESET DEVEDA DATA"
APP_DATA_COLLECTIONS = [
    "user_profiles",
    "user_courses",
    "quiz_progress",
    "quiz_questions",
    "course_catalog",
    "course_curricula",
    "lesson_library",
    "content_intake_sessions",
    "achievements",
    "agent_assignments",
    "agent_threads",
    "agent_messages",
    "agent_artifacts",
]
ALL_COLLECTIONS = ["users", "admins", *APP_DATA_COLLECTIONS]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Reset Deveda MongoDB data with an explicit confirmation phrase.",
    )
    parser.add_argument(
        "--scope",
        choices=["app-data", "all"],
        default="app-data",
        help="`app-data` keeps login accounts; `all` also removes users and admins.",
    )
    parser.add_argument(
        "--confirm",
        required=True,
        help=f'Type exactly "{REQUIRED_CONFIRMATION}" to allow the reset.',
    )
    return parser.parse_args()


def _mask_uri(uri: str) -> str:
    if "@" in uri:
        return uri.split("@", 1)[-1]
    return uri


async def main() -> None:
    load_dotenv(ROOT / ".env")
    args = parse_args()

    if args.confirm != REQUIRED_CONFIRMATION:
        raise SystemExit("Confirmation phrase did not match. No data was deleted.")

    mongo_uri = os.getenv("MONGO_URI")
    db_name = os.getenv("DB_NAME")
    if not mongo_uri or not db_name:
        raise SystemExit("MONGO_URI and DB_NAME must be set before running this script.")

    target_collections = ALL_COLLECTIONS if args.scope == "all" else APP_DATA_COLLECTIONS
    client = AsyncIOMotorClient(mongo_uri)
    db = client[db_name]

    print(f"Resetting `{db_name}` on `{_mask_uri(mongo_uri)}`")
    print(f"Scope: {args.scope}")

    try:
        for name in target_collections:
            result = await db[name].delete_many({})
            print(f"- {name}: deleted {result.deleted_count} document(s)")
    finally:
        client.close()

    print("Database reset complete.")


if __name__ == "__main__":
    asyncio.run(main())
