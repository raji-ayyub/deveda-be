from datetime import datetime
from typing import Optional

from bson import ObjectId
from fastapi import HTTPException, status

from database.database import (
    course_catalog_collection,
    course_curricula_collection,
    lesson_game_progress_collection,
    user_courses_collection,
)
from schemas.schemas import LessonGameProgressUpdate
from services.achievement_services import AchievementService
from services.auth_services import validate_object_id
from services.course_services import ensure_student_account


def serialize_lesson_game_progress(document: Optional[dict], *, course_slug: str, lesson_slug: str, game_key: str) -> dict:
    if not document:
        return {
            "id": None,
            "courseSlug": course_slug,
            "lessonSlug": lesson_slug,
            "gameKey": game_key,
            "status": "not_started",
            "attemptsCount": 0,
            "bestScore": 0,
            "lastScore": 0,
            "totalRounds": 0,
            "completedRounds": 0,
            "bestAccuracy": 0,
            "lastAccuracy": 0,
            "firstCompletedAt": None,
            "masteredAt": None,
            "lastPlayedAt": None,
            "updatedAt": None,
        }

    return {
        "id": str(document["_id"]),
        "courseSlug": document["course_slug"],
        "lessonSlug": document["lesson_slug"],
        "gameKey": document["game_key"],
        "status": document.get("status", "not_started"),
        "attemptsCount": int(document.get("attempts_count", 0) or 0),
        "bestScore": int(document.get("best_score", 0) or 0),
        "lastScore": int(document.get("last_score", 0) or 0),
        "totalRounds": int(document.get("total_rounds", 0) or 0),
        "completedRounds": int(document.get("completed_rounds", 0) or 0),
        "bestAccuracy": int(document.get("best_accuracy", 0) or 0),
        "lastAccuracy": int(document.get("last_accuracy", 0) or 0),
        "firstCompletedAt": document.get("first_completed_at"),
        "masteredAt": document.get("mastered_at"),
        "lastPlayedAt": document.get("last_played_at"),
        "updatedAt": document.get("updated_at"),
    }


def _resolve_status(payload: LessonGameProgressUpdate) -> str:
    if payload.completed and payload.score >= payload.totalRounds and payload.accuracy >= 100:
        return "mastered"
    if payload.completed:
        return "completed"
    if payload.completedRounds > 0 or payload.score > 0:
        return "in_progress"
    return "not_started"


async def _resolve_lesson_game(course_slug: str, lesson_slug: str) -> tuple[dict, dict, dict]:
    course = await course_catalog_collection.find_one({"slug": course_slug})
    if not course:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail={"message": "Course not found"})

    curriculum = await course_curricula_collection.find_one({"course_slug": course_slug})
    if not curriculum:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail={"message": "Course curriculum not found"})

    for module in curriculum.get("modules", []):
        for lesson in module.get("lessons", []):
            if str(lesson.get("slug") or "").strip() != lesson_slug:
                continue
            game_key = str(lesson.get("gameKey") or "").strip()
            if not game_key:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail={"message": "This lesson does not have a game configured"},
                )
            return course, module, lesson

    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail={"message": "Lesson not found in this course"})


async def _ensure_enrollment(user_id: ObjectId, course_slug: str) -> dict:
    enrollment = await user_courses_collection.find_one({"user_id": user_id, "course_slug": course_slug})
    if not enrollment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"message": "Course enrollment not found"},
        )
    return enrollment


class LessonGameService:
    @staticmethod
    async def get_progress(user_id: str, course_slug: str, lesson_slug: str):
        oid = validate_object_id(user_id)
        await ensure_student_account(oid)
        await _ensure_enrollment(oid, course_slug)
        _, _, lesson = await _resolve_lesson_game(course_slug, lesson_slug)
        game_key = str(lesson.get("gameKey") or "").strip()

        progress = await lesson_game_progress_collection.find_one(
            {"user_id": oid, "course_slug": course_slug, "lesson_slug": lesson_slug}
        )

        return {
            "message": "Lesson game progress fetched",
            "data": serialize_lesson_game_progress(progress, course_slug=course_slug, lesson_slug=lesson_slug, game_key=game_key),
        }

    @staticmethod
    async def update_progress(user_id: str, course_slug: str, lesson_slug: str, payload: LessonGameProgressUpdate):
        oid = validate_object_id(user_id)
        await ensure_student_account(oid)
        await _ensure_enrollment(oid, course_slug)
        course, _, lesson = await _resolve_lesson_game(course_slug, lesson_slug)

        lesson_game_key = str(lesson.get("gameKey") or "").strip()
        if payload.gameKey != lesson_game_key:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"message": "Game progress does not match the configured lesson game"},
            )

        existing = await lesson_game_progress_collection.find_one(
            {"user_id": oid, "course_slug": course_slug, "lesson_slug": lesson_slug}
        )
        now = datetime.utcnow()
        next_status = _resolve_status(payload)
        best_score = max(int(existing.get("best_score", 0) or 0), payload.score) if existing else payload.score
        best_accuracy = max(int(existing.get("best_accuracy", 0) or 0), payload.accuracy) if existing else payload.accuracy
        attempts_count = int(existing.get("attempts_count", 0) or 0) + 1 if existing else 1
        first_completed_at = existing.get("first_completed_at") if existing else None
        if payload.completed and first_completed_at is None:
            first_completed_at = now

        mastered_at = existing.get("mastered_at") if existing else None
        if next_status == "mastered" and mastered_at is None:
            mastered_at = now

        document = {
            "user_id": oid,
            "course_slug": course_slug,
            "lesson_slug": lesson_slug,
            "lesson_title": str(lesson.get("title") or "").strip(),
            "game_key": payload.gameKey,
            "status": next_status,
            "attempts_count": attempts_count,
            "best_score": best_score,
            "last_score": payload.score,
            "total_rounds": payload.totalRounds,
            "completed_rounds": payload.completedRounds,
            "best_accuracy": best_accuracy,
            "last_accuracy": payload.accuracy,
            "first_completed_at": first_completed_at,
            "mastered_at": mastered_at,
            "last_played_at": now,
            "updated_at": now,
            "created_at": existing.get("created_at", now) if existing else now,
        }

        await lesson_game_progress_collection.update_one(
            {"user_id": oid, "course_slug": course_slug, "lesson_slug": lesson_slug},
            {"$set": document},
            upsert=True,
        )
        saved = await lesson_game_progress_collection.find_one(
            {"user_id": oid, "course_slug": course_slug, "lesson_slug": lesson_slug}
        )

        awards = await AchievementService.sync_lesson_game_achievement(
            oid,
            course,
            lesson,
            best_score,
            payload.totalRounds,
            best_accuracy,
        )

        return {
            "message": "Lesson game progress updated",
            "data": {
                "progress": serialize_lesson_game_progress(saved, course_slug=course_slug, lesson_slug=lesson_slug, game_key=payload.gameKey),
                "awards": awards,
            },
        }
