from datetime import datetime
from typing import Any

from fastapi import HTTPException, status

from database.database import course_catalog_collection, course_curricula_collection
from schemas.schemas import CourseCurriculumUpsert
from services.lesson_library_services import LessonLibraryService


def _lesson_supports_playground(course: dict, lesson: dict) -> bool:
    lowered_title = lesson.get("title", "").lower()
    lowered_summary = lesson.get("summary", "").lower()
    if lesson.get("contentType") in {"project", "test"}:
        return True
    return any(
        keyword in f"{lowered_title} {lowered_summary}"
        for keyword in ["build", "practice", "implementation", "exercise", "project", "code", "hands-on"]
    )


def _default_learning_objectives(lesson: dict) -> list[str]:
    return [
        f"Explain the core idea behind {lesson.get('title', 'this lesson')} in plain language.",
        "Recognize when to apply the pattern or technique from this lesson.",
        "Complete a small hands-on task before moving to the next lesson.",
    ]


def _default_key_takeaways(lesson: dict) -> list[str]:
    return [
        lesson.get("summary", "Understand the lesson purpose and flow."),
        "Move from concept to application before trying to memorize details.",
        "Use the practice task to confirm the lesson is clear enough to reuse.",
    ]


def _default_learning_flow(title: str, summary: str) -> list[str]:
    focus = title or "this lesson"
    overview = summary or "Understand the idea in context."
    return [
        f"Start with the real problem behind {focus}.",
        f"Break down the core idea: {overview}",
        "Walk through one concrete example before changing anything.",
        "Practice with one guided task and reflect on the result.",
    ]


def _default_content_markdown(course: dict, module_title: str, lesson: dict) -> str:
    course_title = course.get("title", "This course")
    lesson_title = lesson.get("title", "This lesson")
    summary = lesson.get("summary", "")
    return "\n".join(
        [
            f"# {lesson_title}",
            "",
            "## What this lesson is about",
            summary or f"{course_title} uses this lesson to move the learner forward with a practical explanation and a small task.",
            "",
            "## Guided explanation",
            f"This lesson sits inside **{module_title}** and should be taught as a clear progression: explain the idea, show what it looks like, then let the learner try it with support.",
            "",
            "## Teaching sequence",
            "1. Start with the problem this lesson solves.",
            "2. Show the simplest working example first.",
            "3. Point out one common mistake learners make.",
            "4. Let the learner modify the example before moving on.",
            "",
            "## Before moving on",
            "Ask the learner to explain the idea back in their own words and complete the practice task below.",
        ]
    )


def _default_visual_aid_markdown(lesson: dict) -> str:
    lesson_title = lesson.get("title", "This lesson")
    summary = lesson.get("summary", "Understand the concept, then apply it.")
    return "\n".join(
        [
            "## Visual aid",
            f"`Problem` -> `{lesson_title}` -> `Worked example` -> `Guided practice`",
            "",
            f"Use this mental map while studying: {summary}",
        ]
    )


def _default_curriculum_learning_flow(course: dict) -> list[str]:
    title = course.get("title", "This course")
    return [
        f"Orient the learner around the promise of {title}.",
        "Move from fundamentals into guided implementation.",
        "Use checkpoints to confirm understanding before the next module.",
        "Close with milestone work that combines the key ideas.",
    ]


def _default_curriculum_visual_aid(course: dict, modules: list[dict]) -> str:
    module_titles = [module.get("title", f"Module {index}") for index, module in enumerate(modules, start=1)]
    if not module_titles:
        module_titles = ["Orientation", "Guided practice", "Milestone delivery"]
    joined = " -> ".join(f"`{title}`" for title in module_titles[:6])
    return "\n".join(
        [
            "## Course roadmap",
            joined,
            "",
            "Follow the sequence from concept, to guided repetition, to checkpoint, then finish with a visible applied result.",
        ]
    )


def _default_practice_prompt(course: dict, lesson: dict) -> str:
    return (
        f"Use this lesson to create one small working example for **{course.get('title', 'the course')}**. "
        f"Start from the main idea in **{lesson.get('title', 'this lesson')}**, then change one part deliberately and explain what changed."
    )


def _default_playground(course: dict, lesson: dict) -> dict | None:
    if not _lesson_supports_playground(course, lesson):
        return None

    category = course.get("category", "Frontend Development")
    lesson_title = lesson.get("title", "Practice task")

    if category == "Frontend Development":
        return {
            "mode": "web",
            "instructions": f"Use the live workspace to build a small interface for {lesson_title.lower()}. Edit the markup, styles, and behavior until the checks pass.",
            "starterHtml": "<section class=\"lesson-card\">\n  <h1>Hello, learner</h1>\n  <p>Start building from here.</p>\n  <button id=\"action-btn\">Try it</button>\n</section>",
            "starterCss": "body {\n  font-family: 'Segoe UI', sans-serif;\n  padding: 24px;\n  background: #f8fafc;\n}\n\n.lesson-card {\n  max-width: 420px;\n  padding: 24px;\n  border-radius: 20px;\n  background: white;\n  box-shadow: 0 12px 32px rgba(15, 23, 42, 0.08);\n}\n",
            "starterJs": "const button = document.getElementById('action-btn');\nbutton?.addEventListener('click', () => {\n  button.textContent = 'Updated';\n});",
            "checks": [
                {"label": "Add a heading element", "type": "includes", "target": "html", "value": "<h1"},
                {"label": "Style the lesson card", "type": "includes", "target": "css", "value": ".lesson-card"},
                {"label": "Use JavaScript interaction", "type": "includes", "target": "js", "value": "addEventListener"},
            ],
        }

    return {
        "mode": "javascript",
        "instructions": f"Work through the logic for {lesson_title.lower()} using plain JavaScript. Use console output to prove your result.",
        "starterHtml": "",
        "starterCss": "",
        "starterJs": "function solveTask() {\n  const values = [1, 2, 3];\n  return values.map((value) => value * 2);\n}\n\nconsole.log(solveTask());",
        "checks": [
            {"label": "Return a transformed result", "type": "includes", "target": "js", "value": "return"},
            {"label": "Log the outcome", "type": "includes", "target": "js", "value": "console.log"},
        ],
    }


def _lesson_generation_status(lesson: dict) -> str:
    status = str(lesson.get("generationStatus") or "").strip().lower()
    source = str(lesson.get("source") or "").strip().lower()
    if status:
        return status
    title = str(lesson.get("title") or "").strip()
    summary = str(lesson.get("summary") or "").strip()
    default_summary = f"Work through {title} with a guided explanation and one concrete practice step." if title else ""
    default_notes = "Imported from an uploaded source document and normalized for the Deveda lesson renderer."
    content = str(lesson.get("contentMarkdown") or "")
    objectives = lesson.get("learningObjectives") or []
    if (
        source == "agentic_upload"
        and title
        and summary == default_summary
        and str(lesson.get("instructorNotes") or "").strip() == default_notes
        and "## What this lesson is about" in content
        and "## Guided practice" in content
        and len(objectives) == 3
    ):
        return "planned"
    if source in {"scan_plan", "scaffold"}:
        return "planned"
    return "generated"


def _module_generation_status(module: dict) -> str:
    status = str(module.get("generationStatus") or "").strip().lower()
    source = str(module.get("source") or "").strip().lower()
    if status:
        return status
    if source in {"scan_plan", "scaffold"}:
        return "planned"
    return "generated"


def _lesson_is_published(lesson: dict) -> bool:
    return _lesson_generation_status(lesson) == "generated"


def normalize_lesson(course: dict, module_title: str, lesson: dict) -> dict:
    is_planned = _lesson_generation_status(lesson) == "planned"
    normalized = {
        **lesson,
        "libraryLessonSlug": lesson.get("libraryLessonSlug") or lesson.get("slug"),
        "source": lesson.get("source") or "manual",
        "generationStatus": lesson.get("generationStatus") or _lesson_generation_status(lesson),
        "quizId": lesson.get("quizId") or None,
        "quizTitle": lesson.get("quizTitle") or None,
        "learningObjectives": lesson.get("learningObjectives") or ([] if is_planned else _default_learning_objectives(lesson)),
        "keyTakeaways": lesson.get("keyTakeaways") or ([] if is_planned else _default_key_takeaways(lesson)),
        "learningFlow": lesson.get("learningFlow") or ([] if is_planned else _default_learning_flow(lesson.get("title", ""), lesson.get("summary", ""))),
        "contentMarkdown": lesson.get("contentMarkdown") or ("" if is_planned else _default_content_markdown(course, module_title, lesson)),
        "visualAidMarkdown": lesson.get("visualAidMarkdown") if lesson.get("visualAidMarkdown") is not None else ("" if is_planned else _default_visual_aid_markdown(lesson)),
        "practicePrompt": lesson.get("practicePrompt") if lesson.get("practicePrompt") is not None else ("" if is_planned else _default_practice_prompt(course, lesson)),
        "instructorNotes": lesson.get("instructorNotes") or "",
        "playground": lesson.get("playground") if lesson.get("playground") is not None or is_planned else _default_playground(course, lesson),
    }
    return normalized


def normalize_module(course: dict, module: dict) -> dict:
    return {
        **module,
        "source": module.get("source") or "manual",
        "generationStatus": module.get("generationStatus") or _module_generation_status(module),
        "assessmentTitle": module.get("assessmentTitle") or None,
        "assessmentQuizId": module.get("assessmentQuizId") or None,
        "lessons": [normalize_lesson(course, module.get("title", "Module"), lesson) for lesson in module.get("lessons", [])],
    }


def normalize_curriculum_document(course: dict, document: dict) -> dict:
    modules = [normalize_module(course, module) for module in document.get("modules", [])]
    return {
        **document,
        "learning_flow": document.get("learning_flow") or document.get("learningFlow") or _default_curriculum_learning_flow(course),
        "visual_aid_markdown": document.get("visual_aid_markdown") or document.get("visualAidMarkdown") or _default_curriculum_visual_aid(course, modules),
        "modules": modules,
        "milestone_projects": document.get("milestone_projects", []),
    }


def serialize_curriculum(document: dict) -> dict:
    return {
        "id": str(document["_id"]),
        "courseSlug": document["course_slug"],
        "overview": document.get("overview", ""),
        "learningFlow": document.get("learning_flow", []),
        "visualAidMarkdown": document.get("visual_aid_markdown", ""),
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

    scaffold = {
        "course_slug": slug,
        "overview": f"{title} is organized into guided modules with lesson-level practice, checkpoint quizzes, and milestone projects.",
        "learning_flow": _default_curriculum_learning_flow(course),
        "modules": [
            {
                "title": "Foundation Sprint",
                "description": f"Build the core {category.lower()} skills needed for {difficulty.lower()} progression.",
                "order": 1,
                "source": "scaffold",
                "lessons": [
                    {
                "title": f"{title} orientation",
                "slug": f"{slug}-orientation",
                "summary": "Set expectations, tools, and the learning workflow for this path.",
                "durationMinutes": 15,
                "contentType": "lesson",
                "source": "scaffold",
                "generationStatus": "planned",
            },
            {
                "title": "First guided implementation",
                "slug": f"{slug}-first-build",
                "summary": "Ship a small but complete exercise to apply the first module concepts.",
                "durationMinutes": 25,
                "contentType": "lesson",
                "source": "scaffold",
                "generationStatus": "planned",
            },
        ],
                "assessmentTitle": "Module 1 checkpoint quiz",
                "assessmentQuizId": f"{slug}-module-1-quiz",
                "generationStatus": "planned",
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
        "visual_aid_markdown": _default_curriculum_visual_aid(
            course,
            [
                {
                    "title": "Foundation Sprint",
                }
            ],
        ),
        "updated_at": datetime.utcnow(),
        "updated_by": "Deveda Team",
        "is_draft_scaffold": True,
    }
    return normalize_curriculum_document(course, scaffold)


def summarize_curriculum(payload: CourseCurriculumUpsert) -> dict:
    published_modules = [module for module in payload.modules if _module_generation_status(module.dict()) == "generated"]
    total_lessons = sum(1 for module in payload.modules for lesson in module.lessons if _lesson_is_published(lesson.dict()))
    lesson_quizzes = sum(
        1
        for module in payload.modules
        for lesson in module.lessons
        if lesson.quizId and _lesson_is_published(lesson.dict())
    )
    assessment_quizzes = sum(1 for module in published_modules if module.assessmentQuizId)
    total_quizzes = lesson_quizzes + assessment_quizzes
    lesson_duration_minutes = sum(
        lesson.durationMinutes
        for module in payload.modules
        for lesson in module.lessons
        if _lesson_is_published(lesson.dict())
    )
    milestone_duration_minutes = sum(project.estimatedHours * 60 for project in payload.milestoneProjects)

    return {
        "totalLessons": total_lessons,
        "totalQuizzes": total_quizzes,
        "duration": lesson_duration_minutes + milestone_duration_minutes,
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
            normalized = normalize_curriculum_document(course, curriculum)
            normalized["_id"] = curriculum["_id"]
            return {"message": "Course curriculum fetched", "data": serialize_curriculum(normalized)}

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

        normalized_modules = [
            normalize_module(course, module.dict())
            for module in payload.modules
        ]
        update_data: dict[str, Any] = {
            "course_slug": slug,
            "overview": payload.overview,
            "learning_flow": payload.learningFlow,
            "visual_aid_markdown": payload.visualAidMarkdown,
            "modules": normalized_modules,
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

        curriculum_summary = summarize_curriculum(payload)
        await course_catalog_collection.update_one(
            {"slug": slug},
            {
                "$set": {
                    "total_lessons": curriculum_summary["totalLessons"],
                    "total_quizzes": curriculum_summary["totalQuizzes"],
                    "duration": curriculum_summary["duration"],
                    "updated_at": datetime.utcnow(),
                }
            },
        )

        updated = await course_curricula_collection.find_one({"course_slug": slug})
        normalized_updated = normalize_curriculum_document(course, updated)
        normalized_updated["_id"] = updated["_id"]
        await LessonLibraryService.sync_course_lessons(course, normalized_updated, updated_by)
        return {"message": "Course curriculum saved", "data": serialize_curriculum(normalized_updated)}
