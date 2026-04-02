from datetime import datetime
from typing import Optional
from uuid import uuid4

from bson import ObjectId

from database.database import achievements_collection, course_catalog_collection, course_curricula_collection, users_collection
from services.content_services import build_curriculum_scaffold
from services.auth_services import validate_object_id


def serialize_achievement(document: dict) -> dict:
    return {
        "id": str(document["_id"]),
        "userId": str(document["user_id"]),
        "courseSlug": document["course_slug"],
        "courseTitle": document.get("course_title", ""),
        "kind": document["kind"],
        "key": document["key"],
        "title": document["title"],
        "description": document.get("description", ""),
        "celebrationMessage": document.get("celebration_message", ""),
        "badgeLabel": document.get("badge_label", ""),
        "badgeTone": document.get("badge_tone", "blue"),
        "progressTrigger": document.get("progress_trigger", 0),
        "milestoneOrder": document.get("milestone_order"),
        "skills": document.get("skills", []),
        "deliverables": document.get("deliverables", []),
        "parentSummary": document.get("parent_summary", ""),
        "awardedAt": document.get("awarded_at"),
        "certificate": document.get("certificate"),
    }


def _course_skills(course: dict, curriculum: Optional[dict], progress: int) -> list[str]:
    skills = [tag.replace("-", " ").title() for tag in course.get("tags", [])[:4]]
    if curriculum:
        for project in curriculum.get("milestone_projects", [])[:1]:
            skills.extend(project.get("deliverables", [])[:2])
    if progress >= 100:
        skills.append("Independent project delivery")
    return list(dict.fromkeys(skill for skill in skills if skill))


def _parent_summary(course: dict, progress: int, title: str) -> str:
    return (
        f"The learner has reached {progress}% in {course['title']} and earned '{title}', "
        f"showing growing confidence in {course['category'].lower()} work."
    )


def _certificate_payload(course: dict, skills: list[str], awarded_at: datetime) -> dict:
    return {
        "code": f"DEV-{course['slug'].upper().replace('-', '')[:10]}-{uuid4().hex[:8].upper()}",
        "label": "Certificate of Completion",
        "issuedAt": awarded_at,
        "issuer": "Deveda",
        "skills": skills[:5],
        "shareNote": "Share this with a parent, guardian, or mentor to show what the learner can now build.",
    }


async def _award_if_missing(record: dict) -> Optional[dict]:
    existing = await achievements_collection.find_one({"user_id": record["user_id"], "key": record["key"]})
    if existing:
        return None

    result = await achievements_collection.insert_one(record)
    record["_id"] = result.inserted_id
    return record


class AchievementService:
    @staticmethod
    async def sync_course_achievements(user_id: ObjectId, course_slug: str, progress: int, completed: bool):
        course = await course_catalog_collection.find_one({"slug": course_slug})
        if not course:
            return []

        curriculum = await course_curricula_collection.find_one({"course_slug": course_slug})
        if not curriculum:
            curriculum = build_curriculum_scaffold(course)
            result = await course_curricula_collection.insert_one(curriculum)
            curriculum["_id"] = result.inserted_id
        awarded: list[dict] = []

        for milestone in sorted(curriculum.get("milestone_projects", []) if curriculum else [], key=lambda item: item.get("milestoneOrder", 0)):
            threshold = milestone.get("completionThreshold", 100)
            if progress < threshold:
                continue

            awarded_at = datetime.utcnow()
            skills = _course_skills(course, curriculum, progress)
            record = {
                "user_id": user_id,
                "course_slug": course_slug,
                "course_title": course["title"],
                "kind": "milestone",
                "key": f"{course_slug}:milestone:{milestone.get('milestoneOrder', 1)}",
                "title": milestone.get("title", "Milestone unlocked"),
                "description": milestone.get("description", ""),
                "celebration_message": f"You unlocked a new milestone in {course['title']}. Keep the momentum going.",
                "badge_label": f"Milestone {milestone.get('milestoneOrder', 1)}",
                "badge_tone": "amber",
                "progress_trigger": threshold,
                "milestone_order": milestone.get("milestoneOrder"),
                "skills": skills[:4],
                "deliverables": milestone.get("deliverables", []),
                "parent_summary": _parent_summary(course, progress, milestone.get("title", "Milestone unlocked")),
                "awarded_at": awarded_at,
            }
            created = await _award_if_missing(record)
            if created:
                awarded.append(serialize_achievement(created))

        if completed or progress >= 100:
            awarded_at = datetime.utcnow()
            skills = _course_skills(course, curriculum, 100)
            record = {
                "user_id": user_id,
                "course_slug": course_slug,
                "course_title": course["title"],
                "kind": "course_completion",
                "key": f"{course_slug}:course-completion",
                "title": f"{course['title']} completed",
                "description": "The learner completed the full course path and can now showcase the capabilities below.",
                "celebration_message": "Course complete. Your certificate and accolades are ready to share.",
                "badge_label": "Course finisher",
                "badge_tone": "emerald",
                "progress_trigger": 100,
                "skills": skills,
                "deliverables": curriculum.get("milestone_projects", [{}])[-1].get("deliverables", []) if curriculum and curriculum.get("milestone_projects") else [],
                "parent_summary": _parent_summary(course, 100, f"{course['title']} completed"),
                "awarded_at": awarded_at,
                "certificate": _certificate_payload(course, skills, awarded_at),
            }
            created = await _award_if_missing(record)
            if created:
                awarded.append(serialize_achievement(created))

        return awarded

    @staticmethod
    async def sync_lesson_game_achievement(
        user_id: ObjectId,
        course: dict,
        lesson: dict,
        best_score: int,
        total_rounds: int,
        best_accuracy: int,
    ):
        if total_rounds <= 0 or best_score < total_rounds or best_accuracy < 100:
            return []

        lesson_slug = str(lesson.get("slug") or "").strip()
        lesson_title = str(lesson.get("title") or "Lesson").strip() or "Lesson"
        awarded_at = datetime.utcnow()
        record = {
            "user_id": user_id,
            "course_slug": course["slug"],
            "course_title": course["title"],
            "kind": "lesson_game_mastery",
            "key": f"{course['slug']}:lesson-game:{lesson_slug}",
            "title": f"{lesson_title} game mastered",
            "description": f"The learner achieved a perfect run in the {lesson_title.lower()} lesson game.",
            "celebration_message": "Perfect run. You mastered this lesson challenge and locked in the skill.",
            "badge_label": "Game mastery",
            "badge_tone": "violet",
            "progress_trigger": 100,
            "skills": [lesson_title, "Interactive practice", "Lesson reinforcement"],
            "deliverables": ["Perfect lesson game score", "Demonstrated lesson understanding"],
            "parent_summary": (
                f"The learner mastered the interactive challenge for {lesson_title} in {course['title']}, "
                "showing confident understanding through practice."
            ),
            "awarded_at": awarded_at,
        }
        created = await _award_if_missing(record)
        return [serialize_achievement(created)] if created else []

    @staticmethod
    async def get_user_achievements(user_id: str, course_slug: Optional[str] = None):
        oid = validate_object_id(user_id)
        user = await users_collection.find_one({"_id": oid})
        if not user:
            return {"message": "Achievements fetched", "data": []}
        if user.get("role", "Student") != "Student":
            return {"message": "Achievements fetched", "data": []}

        query = {"user_id": oid}
        if course_slug:
            query["course_slug"] = course_slug

        achievements = []
        cursor = achievements_collection.find(query).sort("awarded_at", -1)
        async for achievement in cursor:
            achievements.append(serialize_achievement(achievement))

        return {
            "message": "Achievements fetched",
            "data": achievements,
        }
