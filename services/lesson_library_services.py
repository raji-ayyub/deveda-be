from __future__ import annotations

from datetime import datetime
from typing import Optional

from database.database import course_catalog_collection, lesson_library_collection, user_courses_collection
from services.pagination_utils import build_pagination, normalize_pagination, pagination_slice


def _clean_text(value: Optional[str]) -> str:
    return (value or "").strip()


def _coerce_string_list(values: Optional[list]) -> list[str]:
    if not isinstance(values, list):
        return []
    return [str(value).strip() for value in values if str(value).strip()]


def _lesson_is_publishable(lesson: dict) -> bool:
    status = _clean_text(lesson.get("generationStatus")).lower()
    source = _clean_text(lesson.get("source")).lower()
    if status:
        return status == "generated"
    return source not in {"scan_plan", "scaffold"}


def _looks_like_placeholder_library_item(document: dict) -> bool:
    title = _clean_text(document.get("title"))
    summary = _clean_text(document.get("summary"))
    source = _clean_text(document.get("source")).lower()
    learning_flow = _coerce_string_list(document.get("learning_flow"))
    default_summary = f"Work through {title} with a guided explanation and one concrete practice step." if title else ""
    return (
        source == "agentic_upload"
        and title
        and summary == default_summary
        and bool(learning_flow)
        and learning_flow[0].startswith(f"Start with the problem space around {title}")
    )


def _serialize_course_refs(course_refs: list[dict]) -> list[dict]:
    serialized = []
    for ref in course_refs:
        serialized.append(
            {
                "courseSlug": ref.get("course_slug"),
                "courseTitle": ref.get("course_title", ""),
                "moduleTitle": ref.get("module_title", ""),
                "moduleOrder": ref.get("module_order", 0),
                "lessonSlug": ref.get("lesson_slug", ""),
            }
        )
    return serialized


def serialize_lesson_library_item(document: dict, *, access_status: str = "locked", entry_route: Optional[str] = None) -> dict:
    return {
        "id": str(document["_id"]),
        "slug": document["slug"],
        "title": document.get("title", ""),
        "summary": document.get("summary", ""),
        "durationMinutes": document.get("duration_minutes", 0),
        "contentType": document.get("content_type", "lesson"),
        "source": document.get("source", "manual"),
        "learningObjectives": document.get("learning_objectives", []),
        "keyTakeaways": document.get("key_takeaways", []),
        "learningFlow": document.get("learning_flow", []),
        "visualAidMarkdown": document.get("visual_aid_markdown", ""),
        "courseRefs": _serialize_course_refs(document.get("course_refs", [])),
        "updatedAt": document.get("updated_at"),
        "accessStatus": access_status,
        "entryRoute": entry_route,
    }


class LessonLibraryService:
    @staticmethod
    async def detach_course(course_slug: str) -> dict:
        impacted = await lesson_library_collection.find(
            {"course_refs.course_slug": course_slug},
            {"_id": 1},
        ).to_list(length=500)
        impacted_ids = [document["_id"] for document in impacted]
        if not impacted_ids:
            return {"updated": 0, "deleted": 0}

        await lesson_library_collection.update_many(
            {"_id": {"$in": impacted_ids}},
            {"$pull": {"course_refs": {"course_slug": course_slug}}},
        )
        deleted = await lesson_library_collection.delete_many(
            {
                "_id": {"$in": impacted_ids},
                "course_refs.0": {"$exists": False},
            }
        )
        return {"updated": len(impacted_ids), "deleted": deleted.deleted_count}

    @staticmethod
    async def prune_missing_course_refs() -> None:
        lessons = await lesson_library_collection.find({"course_refs.0": {"$exists": True}}).to_list(length=500)
        if not lessons:
            return

        referenced_slugs = {
            ref.get("course_slug")
            for lesson in lessons
            for ref in lesson.get("course_refs", [])
            if ref.get("course_slug")
        }
        if not referenced_slugs:
            return

        existing_courses = await course_catalog_collection.find(
            {"slug": {"$in": list(referenced_slugs)}},
            {"slug": 1},
        ).to_list(length=len(referenced_slugs))
        valid_slugs = {document.get("slug") for document in existing_courses if document.get("slug")}

        for lesson in lessons:
            course_refs = lesson.get("course_refs", [])
            filtered_refs = [ref for ref in course_refs if ref.get("course_slug") in valid_slugs]
            if len(filtered_refs) == len(course_refs):
                continue
            if filtered_refs:
                await lesson_library_collection.update_one(
                    {"_id": lesson["_id"]},
                    {"$set": {"course_refs": filtered_refs}},
                )
                continue
            await lesson_library_collection.delete_one({"_id": lesson["_id"]})

    @staticmethod
    async def sync_course_lessons(course: dict, curriculum: dict, updated_by: str) -> None:
        course_slug = course["slug"]
        now = datetime.utcnow()

        await lesson_library_collection.update_many(
            {},
            {"$pull": {"course_refs": {"course_slug": course_slug}}},
        )

        for module in curriculum.get("modules", []):
            module_title = _clean_text(module.get("title")) or "Module"
            module_order = int(module.get("order") or 1)
            for lesson in module.get("lessons", []):
                if not _lesson_is_publishable(lesson):
                    continue
                library_slug = _clean_text(lesson.get("libraryLessonSlug")) or _clean_text(lesson.get("slug"))
                if not library_slug:
                    continue

                course_ref = {
                    "course_slug": course_slug,
                    "course_title": course.get("title", ""),
                    "module_title": module_title,
                    "module_order": module_order,
                    "lesson_slug": _clean_text(lesson.get("slug")),
                }
                update_data = {
                    "slug": library_slug,
                    "title": _clean_text(lesson.get("title")),
                    "summary": _clean_text(lesson.get("summary")),
                    "duration_minutes": int(lesson.get("durationMinutes") or 0),
                    "content_type": _clean_text(lesson.get("contentType")) or "lesson",
                    "source": _clean_text(lesson.get("source")) or "manual",
                    "learning_objectives": _coerce_string_list(lesson.get("learningObjectives")),
                    "key_takeaways": _coerce_string_list(lesson.get("keyTakeaways")),
                    "learning_flow": _coerce_string_list(lesson.get("learningFlow")),
                    "visual_aid_markdown": _clean_text(lesson.get("visualAidMarkdown")),
                    "updated_at": now,
                    "updated_by": updated_by,
                }
                await lesson_library_collection.update_one(
                    {"slug": library_slug},
                    {
                        "$set": update_data,
                        "$setOnInsert": {"created_at": now},
                        "$addToSet": {"course_refs": course_ref},
                    },
                    upsert=True,
                )

    @staticmethod
    async def upsert_standalone_lesson(lesson: dict, updated_by: str) -> dict:
        now = datetime.utcnow()
        slug = _clean_text(lesson.get("libraryLessonSlug")) or _clean_text(lesson.get("slug"))
        update_data = {
            "slug": slug,
            "title": _clean_text(lesson.get("title")),
            "summary": _clean_text(lesson.get("summary")),
            "duration_minutes": int(lesson.get("durationMinutes") or 0),
            "content_type": _clean_text(lesson.get("contentType")) or "lesson",
            "source": _clean_text(lesson.get("source")) or "agentic_upload",
            "learning_objectives": _coerce_string_list(lesson.get("learningObjectives")),
            "key_takeaways": _coerce_string_list(lesson.get("keyTakeaways")),
            "learning_flow": _coerce_string_list(lesson.get("learningFlow")),
            "visual_aid_markdown": _clean_text(lesson.get("visualAidMarkdown")),
            "updated_at": now,
            "updated_by": updated_by,
        }
        await lesson_library_collection.update_one(
            {"slug": slug},
            {
                "$set": update_data,
                "$setOnInsert": {"created_at": now, "course_refs": []},
            },
            upsert=True,
        )
        item = await lesson_library_collection.find_one({"slug": slug})
        return serialize_lesson_library_item(item, access_status="draft", entry_route=None)

    @staticmethod
    async def get_library(
        current_user: Optional[dict] = None,
        *,
        search: Optional[str] = None,
        access_status: Optional[str] = None,
        course_slug: Optional[str] = None,
        page: Optional[int] = None,
        page_size: Optional[int] = None,
    ) -> dict:
        await LessonLibraryService.prune_missing_course_refs()
        query = {"course_refs.0": {"$exists": True}}
        lessons = await lesson_library_collection.find(query).sort("updated_at", -1).to_list(length=300)

        enrolled_courses: set[str] = set()
        role = (current_user or {}).get("role")
        if current_user and role == "Student":
            enrollments = await user_courses_collection.find({"user_id": current_user["_id"]}).to_list(length=200)
            enrolled_courses = {item.get("course_slug") for item in enrollments if item.get("course_slug")}

        payload = []
        for lesson in lessons:
            if _looks_like_placeholder_library_item(lesson):
                continue
            course_refs = lesson.get("course_refs", [])
            if role in {"Admin", "Instructor"}:
                entry_route = None
                if course_refs:
                    first_ref = course_refs[0]
                    entry_route = f"/courses/{first_ref.get('course_slug')}/learn?lesson={first_ref.get('lesson_slug')}"
                payload.append(serialize_lesson_library_item(lesson, access_status="available", entry_route=entry_route))
                continue

            accessible_ref = next(
                (ref for ref in course_refs if ref.get("course_slug") in enrolled_courses),
                None,
            )
            access_status = "available" if accessible_ref else "locked"
            entry_route = (
                f"/courses/{accessible_ref.get('course_slug')}/learn?lesson={accessible_ref.get('lesson_slug')}"
                if accessible_ref
                else None
            )
            payload.append(serialize_lesson_library_item(lesson, access_status=access_status, entry_route=entry_route))

        normalized_search = _clean_text(search).lower()
        normalized_access_status = _clean_text(access_status).lower()
        normalized_course_slug = _clean_text(course_slug)

        if normalized_search:
            payload = [
                lesson
                for lesson in payload
                if normalized_search
                in " ".join(
                    [
                        lesson.get("title", ""),
                        lesson.get("summary", ""),
                        " ".join(
                            f"{ref.get('courseTitle', '')} {ref.get('moduleTitle', '')} {ref.get('courseSlug', '')}"
                            for ref in lesson.get("courseRefs", [])
                        ),
                    ]
                ).lower()
            ]

        if normalized_access_status in {"available", "locked", "draft"}:
            payload = [lesson for lesson in payload if lesson.get("accessStatus") == normalized_access_status]

        if normalized_course_slug:
            payload = [
                lesson
                for lesson in payload
                if any(ref.get("courseSlug") == normalized_course_slug for ref in lesson.get("courseRefs", []))
            ]

        summary = {
            "totalLessons": len(payload),
            "availableLessons": len([lesson for lesson in payload if lesson.get("accessStatus") == "available"]),
            "lockedLessons": len([lesson for lesson in payload if lesson.get("accessStatus") == "locked"]),
            "linkedCourses": len(
                {
                    ref.get("courseSlug")
                    for lesson in payload
                    for ref in lesson.get("courseRefs", [])
                    if ref.get("courseSlug")
                }
            ),
            "totalDurationMinutes": sum(int(lesson.get("durationMinutes") or 0) for lesson in payload),
        }

        resolved_page, resolved_page_size = normalize_pagination(page, page_size)
        total_items = len(payload)
        if resolved_page and resolved_page_size:
            start, end = pagination_slice(resolved_page, resolved_page_size)
            payload = payload[start:end]

        response = {"message": "Lesson library fetched", "data": payload, "summary": summary}
        pagination = build_pagination(total_items, resolved_page, resolved_page_size)
        if pagination:
            response["pagination"] = pagination
        return response
