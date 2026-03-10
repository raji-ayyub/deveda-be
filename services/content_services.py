from datetime import datetime

from fastapi import HTTPException, status

from database.database import course_catalog_collection, course_curricula_collection
from schemas.schemas import CourseCurriculumUpsert


def serialize_curriculum(document: dict) -> dict:
    return {
        "id": str(document["_id"]),
        "courseSlug": document["course_slug"],
        "overview": document.get("overview", ""),
        "modules": document.get("modules", []),
        "milestoneProjects": document.get("milestone_projects", []),
        "updatedAt": document.get("updated_at"),
        "updatedBy": document.get("updated_by", "Deveda Team"),
        "isDraftScaffold": document.get("is_draft_scaffold", False),
    }


def build_curriculum_scaffold(course: dict) -> dict:
    title = course["title"]
    slug = course["slug"]
    category = course["category"]
    difficulty = course["difficulty"]

    return {
        "course_slug": slug,
        "overview": f"{title} is organized into guided modules with lesson-level practice, checkpoint quizzes, and milestone projects.",
        "modules": [
            {
                "title": "Foundation Sprint",
                "description": f"Build the core {category.lower()} skills needed for {difficulty.lower()} progression.",
                "order": 1,
                "lessons": [
                    {
                        "title": f"{title} orientation",
                        "slug": f"{slug}-orientation",
                        "summary": "Set expectations, tools, and the learning workflow for this path.",
                        "durationMinutes": 15,
                        "contentType": "lesson",
                    },
                    {
                        "title": "First guided implementation",
                        "slug": f"{slug}-first-build",
                        "summary": "Ship a small but complete exercise to apply the first module concepts.",
                        "durationMinutes": 25,
                        "contentType": "lesson",
                    },
                ],
                "assessmentTitle": "Module 1 checkpoint quiz",
                "assessmentQuizId": f"{slug}-module-1-quiz",
            }
        ],
        "milestone_projects": [
            {
                "title": f"{title} milestone project",
                "description": "Build an end-to-end project that proves readiness for the next stage.",
                "milestoneOrder": 1,
                "estimatedHours": 6,
                "deliverables": [
                    "Working source code",
                    "README with setup instructions",
                    "Reflection on tradeoffs and decisions",
                ],
                "completionThreshold": 70,
            }
        ],
        "updated_at": datetime.utcnow(),
        "updated_by": "Deveda Team",
        "is_draft_scaffold": True,
    }


class ContentService:
    @staticmethod
    async def get_course_curriculum(slug: str):
        course = await course_catalog_collection.find_one({"slug": slug})
        if not course:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"message": "Course not found"},
            )

        curriculum = await course_curricula_collection.find_one({"course_slug": slug})
        if curriculum:
            return {"message": "Course curriculum fetched", "data": serialize_curriculum(curriculum)}

        scaffold = build_curriculum_scaffold(course)
        result = await course_curricula_collection.insert_one(scaffold)
        scaffold["_id"] = result.inserted_id
        return {"message": "Course curriculum scaffold generated", "data": serialize_curriculum(scaffold)}

    @staticmethod
    async def upsert_course_curriculum(slug: str, payload: CourseCurriculumUpsert, updated_by: str):
        course = await course_catalog_collection.find_one({"slug": slug})
        if not course:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"message": "Course not found"},
            )

        update_data = {
            "course_slug": slug,
            "overview": payload.overview,
            "modules": [module.dict() for module in payload.modules],
            "milestone_projects": [project.dict() for project in payload.milestoneProjects],
            "updated_at": datetime.utcnow(),
            "updated_by": updated_by,
            "is_draft_scaffold": False,
        }

        await course_curricula_collection.update_one(
            {"course_slug": slug},
            {"$set": update_data},
            upsert=True,
        )

        updated = await course_curricula_collection.find_one({"course_slug": slug})
        return {"message": "Course curriculum saved", "data": serialize_curriculum(updated)}
