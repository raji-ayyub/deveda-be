import os
from datetime import datetime

from dotenv import load_dotenv
from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo import ASCENDING, DESCENDING

load_dotenv()

MONGO_URI = os.getenv("MONGO_URI")
DB_NAME = os.getenv("DB_NAME")

client = AsyncIOMotorClient(MONGO_URI)
if DB_NAME:
    db = client[DB_NAME]

users_collection = db.users
admins_collection = db.admins
user_profiles_collection = db.user_profiles
user_courses_collection = db.user_courses
quiz_progress_collection = db.quiz_progress
quiz_questions_collection = db.quiz_questions
course_catalog_collection = db.course_catalog
course_curricula_collection = db.course_curricula
lesson_library_collection = db.lesson_library
content_intake_sessions_collection = db.content_intake_sessions
achievements_collection = db.achievements
agent_assignments_collection = db.agent_assignments
agent_threads_collection = db.agent_threads
agent_messages_collection = db.agent_messages
agent_artifacts_collection = db.agent_artifacts
agent_runs_collection = db.agent_runs


def _timestamp_score(value) -> float:
    if isinstance(value, datetime):
        return value.timestamp()
    return 0.0


def _document_priority(document: dict) -> tuple[int, float, float, float]:
    populated_fields = sum(
        1
        for key in ("title", "description", "category", "difficulty", "instructor", "tags", "modules", "milestone_projects")
        if document.get(key)
    )
    object_time = getattr(document.get("_id"), "generation_time", None)
    return (
        populated_fields,
        _timestamp_score(document.get("updated_at")),
        _timestamp_score(document.get("created_at")),
        _timestamp_score(object_time),
    )


async def _dedupe_documents_by_field(collection, field_name: str, label: str) -> None:
    field_ref = f"${field_name}"
    duplicates = await collection.aggregate(
        [
            {
                "$project": {
                    "_id": 1,
                    "dedupe_key": {
                        "$cond": [
                            {"$or": [{"$eq": [field_ref, None]}, {"$eq": [field_ref, ""]}]},
                            "__missing__",
                            field_ref,
                        ]
                    },
                }
            },
            {
                "$group": {
                    "_id": "$dedupe_key",
                    "ids": {"$push": "$_id"},
                    "count": {"$sum": 1},
                }
            },
            {"$match": {"count": {"$gt": 1}}},
        ]
    ).to_list(length=None)

    for duplicate_group in duplicates:
        documents = await collection.find({"_id": {"$in": duplicate_group["ids"]}}).to_list(length=duplicate_group["count"])
        if len(documents) < 2:
            continue

        documents.sort(key=_document_priority, reverse=True)
        ids_to_delete = [document["_id"] for document in documents[1:] if isinstance(document.get("_id"), ObjectId)]
        if not ids_to_delete:
            continue

        await collection.delete_many({"_id": {"$in": ids_to_delete}})
        print(
            f"[startup] Deduplicated {label} for key {duplicate_group['_id']!r}; removed {len(ids_to_delete)} older document(s)."
        )


async def ensure_indexes() -> None:
    await users_collection.create_index([("email", ASCENDING)], unique=True, name="users_email_unique")
    await admins_collection.create_index([("email", ASCENDING)], unique=True, sparse=True, name="admins_email_unique")
    await user_profiles_collection.create_index([("user_id", ASCENDING)], unique=True, name="user_profiles_user_unique")

    await user_courses_collection.create_index(
        [("user_id", ASCENDING), ("course_slug", ASCENDING)],
        unique=True,
        name="user_courses_user_course_unique",
    )
    await user_courses_collection.create_index([("course_slug", ASCENDING)], name="user_courses_course_slug")
    await user_courses_collection.create_index([("last_accessed", DESCENDING)], name="user_courses_last_accessed")

    await quiz_progress_collection.create_index([("user_id", ASCENDING)], name="quiz_progress_user_id")
    await quiz_progress_collection.create_index([("quiz_id", ASCENDING)], name="quiz_progress_quiz_id")
    await quiz_progress_collection.create_index([("attempted_at", DESCENDING)], name="quiz_progress_attempted_at")

    await quiz_questions_collection.create_index([("quiz_id", ASCENDING)], name="quiz_questions_quiz_id")
    await quiz_questions_collection.create_index(
        [("quiz_id", ASCENDING), ("is_active", ASCENDING)],
        name="quiz_questions_quiz_active",
    )

    await _dedupe_documents_by_field(course_catalog_collection, "slug", "course_catalog.slug")
    await course_catalog_collection.create_index([("slug", ASCENDING)], unique=True, name="course_catalog_slug_unique")
    await course_catalog_collection.create_index([("category", ASCENDING)], name="course_catalog_category")
    await course_catalog_collection.create_index([("created_at", DESCENDING)], name="course_catalog_created_at")

    await _dedupe_documents_by_field(course_curricula_collection, "course_slug", "course_curricula.course_slug")
    await course_curricula_collection.create_index(
        [("course_slug", ASCENDING)],
        unique=True,
        name="course_curricula_course_slug_unique",
    )
    await _dedupe_documents_by_field(lesson_library_collection, "slug", "lesson_library.slug")
    await lesson_library_collection.create_index([("slug", ASCENDING)], unique=True, name="lesson_library_slug_unique")
    await lesson_library_collection.create_index([("updated_at", DESCENDING)], name="lesson_library_updated_at")

    await content_intake_sessions_collection.create_index([("user_id", ASCENDING)], name="intake_sessions_user_id")
    await content_intake_sessions_collection.create_index([("course_slug", ASCENDING)], name="intake_sessions_course_slug")
    await content_intake_sessions_collection.create_index([("updated_at", DESCENDING)], name="intake_sessions_updated_at")

    await achievements_collection.create_index(
        [("user_id", ASCENDING), ("course_slug", ASCENDING), ("kind", ASCENDING), ("key", ASCENDING)],
        unique=True,
        name="achievements_user_course_kind_key_unique",
    )
    await achievements_collection.create_index([("awarded_at", DESCENDING)], name="achievements_awarded_at")

    await agent_assignments_collection.create_index([("user_id", ASCENDING)], name="agent_assignments_user_id")
    await agent_assignments_collection.create_index([("status", ASCENDING)], name="agent_assignments_status")
    await agent_assignments_collection.create_index([("updated_at", DESCENDING)], name="agent_assignments_updated_at")

    await agent_threads_collection.create_index([("assignment_id", ASCENDING)], name="agent_threads_assignment_id")
    await agent_threads_collection.create_index([("user_id", ASCENDING)], name="agent_threads_user_id")
    await agent_threads_collection.create_index([("updated_at", DESCENDING)], name="agent_threads_updated_at")

    await agent_messages_collection.create_index(
        [("thread_id", ASCENDING), ("created_at", ASCENDING)],
        name="agent_messages_thread_created",
    )
    await agent_artifacts_collection.create_index([("assignment_id", ASCENDING)], name="agent_artifacts_assignment_id")
    await agent_artifacts_collection.create_index([("user_id", ASCENDING)], name="agent_artifacts_user_id")
    await agent_artifacts_collection.create_index([("created_at", DESCENDING)], name="agent_artifacts_created_at")

    await agent_runs_collection.create_index([("assignment_id", ASCENDING)], name="agent_runs_assignment_id")
    await agent_runs_collection.create_index([("thread_id", ASCENDING)], name="agent_runs_thread_id")
    await agent_runs_collection.create_index([("status", ASCENDING)], name="agent_runs_status")
    await agent_runs_collection.create_index([("updated_at", DESCENDING)], name="agent_runs_updated_at")
