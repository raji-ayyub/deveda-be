import json
import os
import re
import socket
from datetime import datetime
from typing import Any, Optional
from urllib import error, request

from bson import ObjectId
from fastapi import HTTPException, status
from pymongo.errors import PyMongoError

from database.database import (
    achievements_collection,
    agent_assignments_collection,
    agent_artifacts_collection,
    agent_messages_collection,
    agent_runs_collection,
    agent_threads_collection,
    course_catalog_collection,
    course_curricula_collection,
    quiz_progress_collection,
    user_courses_collection,
    users_collection,
)
from services.agent_graph import AgentGraphRuntime
from schemas.schemas import (
    AgentActionCreate,
    AgentApprovalUpdate,
    AgentMessageCreate,
    AgentRequestCreate,
    AgentThreadCreate,
    CourseCatalogCreate,
    CourseCurriculumUpsert,
)
from services.auth_services import require_roles, serialize_user, validate_object_id
from services.content_services import ContentService, build_curriculum_scaffold, normalize_lesson
from services.course_services import CourseCatalogService

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")

AGENT_TEMPLATES = {
    "course_builder": {
        "key": "course_builder",
        "name": "Course Builder",
        "description": "Helps instructors structure courses, lessons, assessments, and examples.",
        "allowedRequesterRoles": ["Instructor"],
        "requiresApproval": True,
        "defaultTitle": "Course Builder Session",
    },
    "progress_analyst": {
        "key": "progress_analyst",
        "name": "Progress Analyst",
        "description": "Monitors learner progress and suggests lesson planning adjustments for instructors.",
        "allowedRequesterRoles": ["Instructor"],
        "requiresApproval": True,
        "defaultTitle": "Progress Analyst Review",
    },
    "lesson_tutor": {
        "key": "lesson_tutor",
        "name": "Nexa",
        "description": "A supportive lesson companion that explains material with examples, analogies, and gentle guidance.",
        "allowedRequesterRoles": ["Student", "Instructor"],
        "requiresApproval": True,
        "defaultTitle": "Nexa Chat",
    },
    "platform_support": {
        "key": "platform_support",
        "name": "Platform Support",
        "description": "Guides users through navigation, workflows, and recent platform capabilities.",
        "allowedRequesterRoles": ["Student", "Instructor"],
        "requiresApproval": True,
        "defaultTitle": "Platform Support",
    },
}

PLATFORM_AREAS = [
    {"name": "Course catalog", "route": "/courses", "description": "Browse coding tracks, view details, and start learner enrollments."},
    {"name": "Learner profile", "route": "/profile", "description": "Shows student progress, certificates, achievements, and active courses."},
    {"name": "Instructor dashboard", "route": "/instructor/dashboard", "description": "Handles course management, curriculum, quizzes, and analytics for instructors."},
    {"name": "Instructor profile", "route": "/instructor/profile", "description": "Shows instructor identity, teaching workspace links, and platform teaching snapshot."},
    {"name": "Admin dashboard", "route": "/admin/dashboard", "description": "Manages users, approvals, analytics, and platform operations."},
    {"name": "Account settings", "route": "/settings", "description": "Updates name, email, avatar, and password."},
]


def _normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9\s-]", " ", value.lower())).strip()


def _token_set(value: str) -> set[str]:
    return {token for token in _normalize_text(value).replace("-", " ").split() if token}


def _slugify_title(value: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return normalized or "new-course"


def _infer_course_category(message: str) -> str:
    lowered = _normalize_text(message)
    if any(keyword in lowered for keyword in ["backend", "api", "database", "server", "fastapi", "django", "node"]):
        return "Backend Development"
    if any(keyword in lowered for keyword in ["system", "architecture", "distributed", "scalability", "design"]):
        return "Systems Design"
    return "Frontend Development"


def _infer_course_difficulty(message: str) -> str:
    lowered = _normalize_text(message)
    if "mastery" in lowered:
        return "Mastery"
    if "advanced" in lowered:
        return "Advanced"
    if "intermediate" in lowered:
        return "Intermediate"
    return "Beginner"


def _extract_course_title(message: str) -> Optional[str]:
    stripped = message.strip()
    quoted = re.search(r"['\"]([^'\"]{3,80})['\"]", stripped)
    if quoted:
        return quoted.group(1).strip()

    patterns = [
        r"(?:create|build|make|start)\s+(?:a\s+|an\s+)?(?:new\s+)?course\s+(?:called|named|titled)\s+(.+?)(?:\s+for\s+|\s+with\s+|$)",
        r"(?:create|build|make|start)\s+(?:a\s+|an\s+)?(.+?)\s+course(?:\s+for|\s+with|$)",
    ]
    for pattern in patterns:
        match = re.search(pattern, stripped, flags=re.IGNORECASE)
        if match:
            title = match.group(1).strip(" .,:;-")
            if len(title) >= 3:
                return title
    return None


def _default_course_tags(category: str, title: str) -> list[str]:
    title_tokens = [token for token in _token_set(title) if len(token) > 2][:2]
    category_tags = {
        "Frontend Development": ["html", "css", "javascript"],
        "Backend Development": ["api", "database", "server"],
        "Systems Design": ["architecture", "scalability", "tradeoffs"],
    }
    return list(dict.fromkeys([*title_tokens, *category_tags.get(category, [])]))[:5]


def _serialize_assignment(document: dict) -> dict:
    return {
        "id": str(document["_id"]),
        "userId": str(document["user_id"]),
        "requestedBy": document.get("requested_by"),
        "targetUserId": str(document["target_user_id"]) if document.get("target_user_id") else None,
        "agentType": document["agent_type"],
        "displayName": document.get("display_name"),
        "notes": document.get("notes", ""),
        "courseSlug": document.get("course_slug"),
        "lessonSlug": document.get("lesson_slug"),
        "status": document.get("status", "pending"),
        "adminNotes": document.get("admin_notes", ""),
        "approvedBy": str(document["approved_by"]) if document.get("approved_by") else None,
        "approvedAt": document.get("approved_at"),
        "createdAt": document.get("created_at"),
        "updatedAt": document.get("updated_at"),
    }


def _serialize_thread(document: dict, assignment: Optional[dict] = None, preview: Optional[str] = None) -> dict:
    return {
        "id": str(document["_id"]),
        "assignmentId": str(document["assignment_id"]),
        "userId": str(document["user_id"]),
        "title": document.get("title"),
        "agentType": document.get("agent_type"),
        "context": document.get("context", {}),
        "lastMessagePreview": preview or document.get("last_message_preview", ""),
        "createdAt": document.get("created_at"),
        "updatedAt": document.get("updated_at"),
        "assignment": _serialize_assignment(assignment) if assignment else None,
    }


def _serialize_artifact(document: dict) -> dict:
    return {
        "id": str(document["_id"]),
        "assignmentId": str(document["assignment_id"]),
        "threadId": str(document["thread_id"]) if document.get("thread_id") else None,
        "userId": str(document["user_id"]),
        "agentType": document["agent_type"],
        "artifactType": document["artifact_type"],
        "title": document["title"],
        "summary": document.get("summary", ""),
        "status": document.get("status", "generated"),
        "route": document.get("route"),
        "payload": document.get("payload", {}),
        "createdAt": document.get("created_at"),
    }


def _serialize_message(document: dict) -> dict:
    return {
        "id": str(document["_id"]),
        "threadId": str(document["thread_id"]),
        "role": document["role"],
        "content": document["content"],
        "metadata": document.get("metadata", {}),
        "createdAt": document.get("created_at"),
    }


def _request_requires_approval(template: dict, current_user: dict) -> bool:
    return bool(template.get("requiresApproval", True)) and current_user.get("role") != "Admin"


def _assignment_identity_query(
    *,
    user_id: ObjectId,
    agent_type: str,
    target_user_id: Optional[ObjectId] = None,
    course_slug: Optional[str] = None,
    lesson_slug: Optional[str] = None,
) -> dict:
    return {
        "user_id": user_id,
        "agent_type": agent_type,
        "target_user_id": target_user_id,
        "course_slug": course_slug,
        "lesson_slug": lesson_slug,
    }


def _actor_label(user: dict) -> str:
    return f"{user.get('first_name', '')} {user.get('last_name', '')}".strip() or user.get("email", "Deveda Agent")


async def _start_agent_run(
    assignment: dict,
    *,
    run_type: str,
    current_user: dict,
    thread: Optional[dict] = None,
    payload: Optional[dict] = None,
) -> dict:
    now = datetime.utcnow()
    document = {
        "assignment_id": assignment["_id"],
        "thread_id": thread["_id"] if thread else None,
        "user_id": assignment["user_id"],
        "agent_type": assignment["agent_type"],
        "run_type": run_type,
        "status": "running",
        "started_by": current_user["_id"],
        "steps": [],
        "payload": payload or {},
        "created_at": now,
        "updated_at": now,
    }
    result = await agent_runs_collection.insert_one(document)
    document["_id"] = result.inserted_id
    return document


async def _finish_agent_run(
    run_id: ObjectId,
    *,
    status_value: str,
    steps: Optional[list[str]] = None,
    output: Optional[dict] = None,
    error_message: Optional[str] = None,
) -> None:
    update_data = {
        "status": status_value,
        "updated_at": datetime.utcnow(),
    }
    if steps is not None:
        update_data["steps"] = steps
    if output is not None:
        update_data["output"] = output
    if error_message is not None:
        update_data["error"] = error_message

    await agent_runs_collection.update_one({"_id": run_id}, {"$set": update_data})


async def _get_user_or_404(user_id: ObjectId) -> dict:
    user = await users_collection.find_one({"_id": user_id})
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"message": "User not found"},
        )
    return user


async def _get_assignment_or_404(assignment_id: str) -> dict:
    assignment = await agent_assignments_collection.find_one({"_id": validate_object_id(assignment_id)})
    if not assignment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"message": "Agent assignment not found"},
        )
    return assignment


async def _get_thread_or_404(thread_id: str) -> dict:
    thread = await agent_threads_collection.find_one({"_id": validate_object_id(thread_id)})
    if not thread:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"message": "Agent thread not found"},
        )
    return thread


async def _get_artifact_or_404(artifact_id: str) -> dict:
    artifact = await agent_artifacts_collection.find_one({"_id": validate_object_id(artifact_id)})
    if not artifact:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"message": "Agent artifact not found"},
        )
    return artifact


def _ensure_assignment_access(current_user: dict, assignment: dict) -> None:
    if str(assignment["user_id"]) == str(current_user["_id"]) or current_user.get("role") == "Admin":
        return
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail={"message": "You do not have access to this agent assignment"},
    )


def _ensure_thread_access(current_user: dict, thread: dict) -> None:
    if str(thread["user_id"]) == str(current_user["_id"]) or current_user.get("role") == "Admin":
        return
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail={"message": "You do not have access to this agent thread"},
    )


async def _store_message(thread_id: ObjectId, role: str, content: str, metadata: Optional[dict] = None) -> dict:
    document = {
        "thread_id": thread_id,
        "role": role,
        "content": content,
        "metadata": metadata or {},
        "created_at": datetime.utcnow(),
    }
    result = await agent_messages_collection.insert_one(document)
    document["_id"] = result.inserted_id
    return document


async def _store_artifact(
    assignment: dict,
    artifact_type: str,
    title: str,
    summary: str,
    payload: dict,
    *,
    thread_id: Optional[ObjectId] = None,
    route: Optional[str] = None,
) -> dict:
    document = {
        "assignment_id": assignment["_id"],
        "thread_id": thread_id,
        "user_id": assignment["user_id"],
        "agent_type": assignment["agent_type"],
        "artifact_type": artifact_type,
        "title": title,
        "summary": summary,
        "status": "generated",
        "route": route,
        "payload": payload,
        "created_at": datetime.utcnow(),
    }
    try:
        result = await agent_artifacts_collection.insert_one(document)
    except PyMongoError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "message": (
                    "The generated artifact could not be stored right now. "
                    "Use the lighter course outline flow or generate one module at a time."
                )
            },
        ) from exc
    document["_id"] = result.inserted_id
    return document


async def _fetch_recent_messages(thread_id: ObjectId, limit: int = 8) -> list[dict]:
    messages = await agent_messages_collection.find({"thread_id": thread_id}).sort("created_at", -1).to_list(length=limit)
    return list(reversed(messages))


async def _collect_platform_context(current_user: dict) -> dict:
    course_count = await course_catalog_collection.count_documents({})
    areas = PLATFORM_AREAS[:]
    if current_user.get("role") == "Student":
        areas = [area for area in areas if not area["route"].startswith("/admin") and not area["route"].startswith("/instructor")]
    return {
        "courseCount": course_count,
        "areas": areas,
    }


async def _find_course_from_reference(reference: Optional[str], message: str) -> Optional[dict]:
    if reference:
        course = await course_catalog_collection.find_one({"slug": reference})
        if course:
            return course

    normalized_message = _normalize_text(message)
    message_tokens = _token_set(message)
    if not normalized_message:
        return None

    courses = await course_catalog_collection.find().to_list(length=200)
    best_course = None
    best_score = 0.0

    for course in courses:
        title = course.get("title", "")
        slug = course.get("slug", "")
        normalized_title = _normalize_text(title)
        normalized_slug = _normalize_text(slug.replace("-", " "))
        title_tokens = _token_set(title)
        slug_tokens = _token_set(slug)

        token_overlap = 0.0
        if title_tokens:
            token_overlap = len(title_tokens & message_tokens) / len(title_tokens)

        score = token_overlap
        if normalized_title and normalized_title in normalized_message:
            score += 2.0
        if normalized_slug and normalized_slug in normalized_message:
            score += 1.5
        if slug_tokens:
            score += len(slug_tokens & message_tokens) / max(len(slug_tokens), 1) * 0.5

        if score > best_score:
            best_score = score
            best_course = course

    return best_course if best_score >= 0.6 else None


async def _collect_course_context(course_slug: Optional[str], lesson_slug: Optional[str], message: str) -> dict:
    course = await _find_course_from_reference(course_slug, message)
    if not course:
        return {}

    course_slug = course.get("slug")
    curriculum = await course_curricula_collection.find_one({"course_slug": course_slug})
    lesson = None
    if curriculum and lesson_slug:
        for module in curriculum.get("modules", []):
            for item in module.get("lessons", []):
                if item.get("slug") == lesson_slug:
                    lesson = {
                        **item,
                        "moduleTitle": module.get("title"),
                        "moduleOrder": module.get("order"),
                    }
                    break
            if lesson:
                break

    return {
        "course": course,
        "curriculum": curriculum,
        "lesson": lesson,
        "matchedCourseSlug": course_slug,
    }


async def _collect_progress_context(target_user_id: Optional[ObjectId]) -> dict:
    if not target_user_id:
        return {}

    learner = await users_collection.find_one({"_id": target_user_id})
    if not learner:
        return {}

    courses = await user_courses_collection.find({"user_id": target_user_id}).sort("last_accessed", -1).to_list(length=12)
    quizzes = await quiz_progress_collection.find({"user_id": target_user_id}).sort("attempted_at", -1).to_list(length=12)
    achievements = await achievements_collection.find({"user_id": target_user_id}).sort("awarded_at", -1).to_list(length=8)

    completed_courses = len([course for course in courses if course.get("completed")])
    average_progress = round(sum(course.get("progress", 0) for course in courses) / len(courses)) if courses else 0
    pass_rate = round((len([quiz for quiz in quizzes if quiz.get("passed")]) / len(quizzes)) * 100) if quizzes else 0

    return {
        "learner": serialize_user(learner),
        "courses": courses,
        "quizzes": quizzes,
        "achievements": achievements,
        "summary": {
            "completedCourses": completed_courses,
            "averageProgress": average_progress,
            "passRate": pass_rate,
        },
    }


def _course_builder_reply(message: str, context: dict) -> str:
    course = context.get("course")
    curriculum = context.get("curriculum") or {}
    module_count = len(curriculum.get("modules", []))
    milestone_count = len(curriculum.get("milestone_projects", []))

    if not course:
        return (
            "I can help shape this course. Start by naming the outcome, the learner level, and one concrete project the learner should finish. "
            "A strong first pass is: 1. foundations, 2. guided build, 3. independent extension, 4. quiz checkpoint, 5. milestone project.\n\n"
            "If you want, send me the course title and target level and I will draft the module flow next."
        )

    return (
        f"For `{course['title']}`, keep the teaching arc simple: introduce the idea, model it, let learners practice it, then close with a project.\n\n"
        f"Current shape: {module_count} modules and {milestone_count} milestone projects. "
        f"Based on your note, I would tighten the course around one central promise: what the learner can build by the end.\n\n"
        f"Recommended next move:\n"
        f"1. Open with a concrete build outcome in the first module.\n"
        f"2. Break each major concept into one lesson, one applied example, and one misconception to correct.\n"
        f"3. End each module with a mini checkpoint before the next concept.\n"
        f"4. Use a final milestone project that combines the most important skills.\n\n"
        f"Teaching example: if the concept feels abstract, explain it as a story about a real developer task, then show the code version immediately after."
    )


def _course_summary_reply(context: dict) -> str:
    course = context.get("course")
    curriculum = context.get("curriculum") or {}
    if not course:
        return "I could not match that to a course on the platform yet. Mention the course title again and I will scan the catalog more precisely."

    total_lessons = course.get("totalLessons", course.get("total_lessons", 0))
    total_quizzes = course.get("totalQuizzes", course.get("total_quizzes", 0))
    duration = course.get("duration", 0)
    modules = curriculum.get("modules", [])
    milestones = curriculum.get("milestone_projects", [])
    module_titles = ", ".join(module.get("title", "Module") for module in modules[:4]) or "No detailed modules published yet"
    milestone_titles = ", ".join(item.get("title", "Milestone") for item in milestones[:2]) or "No milestone project listed yet"

    evidence_score = 0
    evidence_score += 1 if total_lessons >= 8 else 0
    evidence_score += 1 if total_quizzes >= 3 else 0
    evidence_score += 1 if len(modules) >= 3 else 0
    evidence_score += 1 if len(milestones) >= 1 else 0
    evidence_score += 1 if len(course.get("tags", [])) >= 3 else 0

    if evidence_score >= 4:
        verdict = "My view: this looks effective for beginners because it has enough structure, practice checkpoints, and progression signals."
    elif evidence_score >= 2:
        verdict = "My view: this is a reasonable beginner foundation, but it would become stronger with more explicit checkpoints and project-driven reinforcement."
    else:
        verdict = "My view: the foundation is present, but the course looks too thin right now to be consistently strong for beginners."

    overview = curriculum.get("overview") or course.get("description", "")

    return (
        f"Yes. I found the real course on the platform: `{course['title']}`.\n\n"
        f"Summary:\n"
        f"- Category: {course.get('category')}\n"
        f"- Difficulty: {course.get('difficulty')}\n"
        f"- Lessons: {total_lessons}\n"
        f"- Quizzes: {total_quizzes}\n"
        f"- Duration: {duration} minutes\n"
        f"- Focus: {overview}\n"
        f"- Main module flow: {module_titles}\n"
        f"- Milestone path: {milestone_titles}\n\n"
        f"{verdict}\n\n"
        f"Why I say that: the course already points learners toward {', '.join(course.get('tags', [])[:4]) or 'core frontend skills'}, which is the right shape for a beginner track. "
        f"If you want, I can now give you a sharper instructional review and specific improvements module by module."
    )


def _module_to_markdown(module: dict, index: int) -> str:
    lesson_titles = ", ".join(lesson.get("title", "Lesson") for lesson in module.get("lessons", [])[:3])
    return (
        f"{index}. **{module['title']}**\n"
        f"   - Why add it: {module['description']}\n"
        f"   - Starter lessons: {lesson_titles}\n"
        f"   - Checkpoint: {module.get('assessmentTitle', 'Module checkpoint')}"
    )


def _build_frontend_extension_modules(course: dict, starting_order: int) -> list[dict]:
    slug = course["slug"]
    return [
        {
            "title": "JavaScript for Real Interfaces",
            "description": "Move beyond syntax into the browser behaviors that make pages interactive and easier to reason about.",
            "order": starting_order,
            "lessons": [
                {
                    "title": "State changes in the browser",
                    "slug": f"{slug}-state-changes-browser",
                    "summary": "Show how user actions, form input, and UI state connect to JavaScript updates on a real page.",
                    "durationMinutes": 20,
                    "contentType": "lesson",
                },
                {
                    "title": "DOM events with mini interactions",
                    "slug": f"{slug}-dom-events-mini-interactions",
                    "summary": "Build small interface interactions so learners see why events matter immediately.",
                    "durationMinutes": 25,
                    "contentType": "lesson",
                },
                {
                    "title": "Mini project: interactive landing section",
                    "slug": f"{slug}-interactive-landing-section",
                    "summary": "Combine event handling, toggles, and DOM updates inside one compact exercise.",
                    "durationMinutes": 30,
                    "contentType": "project",
                },
            ],
            "assessmentTitle": "JavaScript interface quiz",
            "assessmentQuizId": f"{slug}-javascript-interface-quiz",
        },
        {
            "title": "Accessibility and Semantic Frontend",
            "description": "Teach learners to build pages that work for more users and reinforce correct HTML structure at the same time.",
            "order": starting_order + 1,
            "lessons": [
                {
                    "title": "Semantic HTML that communicates meaning",
                    "slug": f"{slug}-semantic-html-meaning",
                    "summary": "Use semantic tags to make layout, hierarchy, and purpose clearer for humans and assistive tools.",
                    "durationMinutes": 18,
                    "contentType": "lesson",
                },
                {
                    "title": "Keyboard navigation and focus states",
                    "slug": f"{slug}-keyboard-navigation-focus",
                    "summary": "Practice building pages that can be navigated without a mouse.",
                    "durationMinutes": 20,
                    "contentType": "lesson",
                },
                {
                    "title": "Accessibility review workshop",
                    "slug": f"{slug}-accessibility-review-workshop",
                    "summary": "Audit an earlier page and improve contrast, labels, and focus behavior.",
                    "durationMinutes": 22,
                    "contentType": "lesson",
                },
            ],
            "assessmentTitle": "Accessibility checkpoint",
            "assessmentQuizId": f"{slug}-accessibility-checkpoint",
        },
        {
            "title": "Debugging and Browser Developer Tools",
            "description": "Beginners become faster when they can inspect, trace, and fix their own mistakes instead of waiting for rescue.",
            "order": starting_order + 2,
            "lessons": [
                {
                    "title": "Inspect elements and trace styles",
                    "slug": f"{slug}-inspect-elements-styles",
                    "summary": "Use DevTools to find broken spacing, inherited styles, and missing selectors.",
                    "durationMinutes": 18,
                    "contentType": "lesson",
                },
                {
                    "title": "Console debugging for beginners",
                    "slug": f"{slug}-console-debugging-beginners",
                    "summary": "Learn when to log values, inspect events, and narrow down errors without panic.",
                    "durationMinutes": 20,
                    "contentType": "lesson",
                },
                {
                    "title": "Fix-a-broken-page challenge",
                    "slug": f"{slug}-fix-broken-page-challenge",
                    "summary": "Repair a deliberately broken page by following a structured debugging process.",
                    "durationMinutes": 30,
                    "contentType": "project",
                },
            ],
            "assessmentTitle": "Debugging skills check",
            "assessmentQuizId": f"{slug}-debugging-skills-check",
        },
        {
            "title": "Git, GitHub, and Deployment Basics",
            "description": "Students should leave the beginner track knowing how to save work, share progress, and publish a simple project.",
            "order": starting_order + 3,
            "lessons": [
                {
                    "title": "Version control in plain language",
                    "slug": f"{slug}-version-control-plain-language",
                    "summary": "Explain commits, branches, and repositories using beginner-friendly project stories.",
                    "durationMinutes": 15,
                    "contentType": "lesson",
                },
                {
                    "title": "Push a project to GitHub",
                    "slug": f"{slug}-push-project-github",
                    "summary": "Walk through connecting a local frontend project to GitHub for backup and sharing.",
                    "durationMinutes": 20,
                    "contentType": "lesson",
                },
                {
                    "title": "Deploy your first site",
                    "slug": f"{slug}-deploy-first-site",
                    "summary": "Publish a project so learners can send a real link to friends, parents, or mentors.",
                    "durationMinutes": 25,
                    "contentType": "project",
                },
            ],
            "assessmentTitle": "Git and deployment quiz",
            "assessmentQuizId": f"{slug}-git-deployment-quiz",
        },
        {
            "title": "Performance and Responsive Polish",
            "description": "Add a final layer of frontend judgment so learners can make pages feel lighter, cleaner, and more intentional.",
            "order": starting_order + 4,
            "lessons": [
                {
                    "title": "Responsive layout review",
                    "slug": f"{slug}-responsive-layout-review",
                    "summary": "Improve an existing layout for mobile and tablet without rebuilding it from zero.",
                    "durationMinutes": 18,
                    "contentType": "lesson",
                },
                {
                    "title": "Image and asset optimization basics",
                    "slug": f"{slug}-image-asset-optimization-basics",
                    "summary": "Introduce practical performance wins like smaller images, better loading, and cleaner asset choices.",
                    "durationMinutes": 18,
                    "contentType": "lesson",
                },
                {
                    "title": "Final polish studio",
                    "slug": f"{slug}-final-polish-studio",
                    "summary": "Refine a course project with responsiveness, accessibility, and performance improvements.",
                    "durationMinutes": 30,
                    "contentType": "project",
                },
            ],
            "assessmentTitle": "Polish and performance review",
            "assessmentQuizId": f"{slug}-polish-performance-review",
        },
    ]


def _build_generic_extension_modules(course: dict, starting_order: int) -> list[dict]:
    slug = course["slug"]
    category_label = course.get("category", "coding").lower()
    return [
        {
            "title": "Applied Practice Studio",
            "description": f"Turn the first {category_label} concepts into repeated practice with guided examples.",
            "order": starting_order,
            "lessons": [
                {
                    "title": "Worked example lab",
                    "slug": f"{slug}-worked-example-lab",
                    "summary": "Break one important concept into a guided exercise with commentary at each step.",
                    "durationMinutes": 20,
                    "contentType": "lesson",
                },
                {
                    "title": "Modify the example",
                    "slug": f"{slug}-modify-the-example",
                    "summary": "Ask learners to change one working example instead of building from zero.",
                    "durationMinutes": 18,
                    "contentType": "lesson",
                },
            ],
            "assessmentTitle": "Applied practice check",
            "assessmentQuizId": f"{slug}-applied-practice-check",
        },
        {
            "title": "Debugging and Repair",
            "description": "Beginners learn faster when they are shown how to find and fix mistakes calmly.",
            "order": starting_order + 1,
            "lessons": [
                {
                    "title": "Spot the mistake",
                    "slug": f"{slug}-spot-the-mistake",
                    "summary": "Show common beginner mistakes and the fastest way to diagnose each one.",
                    "durationMinutes": 18,
                    "contentType": "lesson",
                },
                {
                    "title": "Repair challenge",
                    "slug": f"{slug}-repair-challenge",
                    "summary": "Let learners fix a broken implementation and explain what changed.",
                    "durationMinutes": 22,
                    "contentType": "project",
                },
            ],
            "assessmentTitle": "Repair checkpoint",
            "assessmentQuizId": f"{slug}-repair-checkpoint",
        },
        {
            "title": "Workflow and Delivery",
            "description": "Add the habits learners need to organize work, save progress, and share outcomes.",
            "order": starting_order + 2,
            "lessons": [
                {
                    "title": "Organize project work",
                    "slug": f"{slug}-organize-project-work",
                    "summary": "Teach a simple workflow for naming, saving, and reviewing practical work.",
                    "durationMinutes": 15,
                    "contentType": "lesson",
                },
                {
                    "title": "Share your output",
                    "slug": f"{slug}-share-your-output",
                    "summary": "Guide learners on how to present work clearly to an instructor, parent, or teammate.",
                    "durationMinutes": 20,
                    "contentType": "lesson",
                },
            ],
            "assessmentTitle": "Workflow review",
            "assessmentQuizId": f"{slug}-workflow-review",
        },
        {
            "title": "Performance and Quality",
            "description": "Introduce a light quality mindset so learners can improve what they already built.",
            "order": starting_order + 3,
            "lessons": [
                {
                    "title": "Quality checklist",
                    "slug": f"{slug}-quality-checklist",
                    "summary": "Use a short checklist to improve clarity, correctness, and user experience.",
                    "durationMinutes": 16,
                    "contentType": "lesson",
                },
                {
                    "title": "Improve the project",
                    "slug": f"{slug}-improve-the-project",
                    "summary": "Revisit an earlier project and apply a targeted improvement pass.",
                    "durationMinutes": 22,
                    "contentType": "project",
                },
            ],
            "assessmentTitle": "Quality checkpoint",
            "assessmentQuizId": f"{slug}-quality-checkpoint",
        },
        {
            "title": "Capstone Preparation",
            "description": "Set up the learner for a final piece of work that proves readiness for the next stage.",
            "order": starting_order + 4,
            "lessons": [
                {
                    "title": "Plan the capstone",
                    "slug": f"{slug}-plan-the-capstone",
                    "summary": "Choose a small but complete final build and break it into manageable steps.",
                    "durationMinutes": 18,
                    "contentType": "lesson",
                },
                {
                    "title": "Capstone kickoff",
                    "slug": f"{slug}-capstone-kickoff",
                    "summary": "Start the capstone with clear requirements, starter scaffolding, and review criteria.",
                    "durationMinutes": 24,
                    "contentType": "project",
                },
            ],
            "assessmentTitle": "Capstone readiness check",
            "assessmentQuizId": f"{slug}-capstone-readiness-check",
        },
    ]


def _build_extension_modules(course: dict, curriculum: Optional[dict]) -> list[dict]:
    existing_module_count = len((curriculum or {}).get("modules", []))
    starting_order = existing_module_count + 1
    if course.get("category") == "Frontend Development":
        return _build_frontend_extension_modules(course, starting_order)
    return _build_generic_extension_modules(course, starting_order)


def _build_course_improvement_reply(context: dict) -> str:
    course = context.get("course")
    curriculum = context.get("curriculum") or {}
    if not course:
        return "Name the course again and I will scan the platform catalog before suggesting additions."

    suggested_modules = _build_extension_modules(course, curriculum)
    module_lines = "\n".join(_module_to_markdown(module, index) for index, module in enumerate(suggested_modules, start=1))
    existing_count = len(curriculum.get("modules", []))

    return (
        f"I reviewed `{course['title']}` and it already covers the base beginner promise well: {course.get('description', '').strip()}\n\n"
        f"To make it stronger, I would keep the current {existing_count or 1}-module foundation and add these 5 modules next:\n\n"
        f"{module_lines}\n\n"
        "Why this improves the course: it closes the gap between basic syntax learning and practical frontend confidence. "
        "Learners would leave with better debugging habits, stronger accessibility instincts, a clearer delivery workflow, and a more portfolio-ready finish.\n\n"
        "If you want me to carry it forward, I can create the first structured draft for these modules immediately."
    )


def _build_curriculum_draft_payload(
    course: dict,
    curriculum: Optional[dict],
    instruction: str,
    suggested_modules: Optional[list[dict]] = None,
) -> dict:
    base = curriculum or build_curriculum_scaffold(course)
    modules = list(base.get("modules", []))
    milestones = list(base.get("milestone_projects", []))
    title = course["title"]
    category = course["category"]
    difficulty = course["difficulty"]
    tags = course.get("tags", [])

    if suggested_modules:
        modules.extend(suggested_modules)
    elif len(modules) < 3:
        modules.extend([
            {
                "title": "Concept Building",
                "description": f"Turn the first core {category.lower()} ideas into repeatable patterns through guided examples.",
                "order": len(modules) + 1,
                "lessons": [
                    {
                        "title": f"{title} worked examples",
                        "slug": f"{course['slug']}-worked-examples",
                        "summary": "Break down the core ideas with short examples and explain the reasoning behind each move.",
                        "durationMinutes": 20,
                        "contentType": "lesson",
                    },
                    {
                        "title": "Common mistakes clinic",
                        "slug": f"{course['slug']}-mistakes-clinic",
                        "summary": "Show typical beginner mistakes and how to fix them without frustration.",
                        "durationMinutes": 15,
                        "contentType": "lesson",
                    },
                ],
                "assessmentTitle": f"{title} concept check",
                "assessmentQuizId": f"{course['slug']}-concept-check",
            },
            {
                "title": "Project Lift-Off",
                "description": f"Guide learners into a small {difficulty.lower()} project that turns abstract lessons into something visible and satisfying.",
                "order": len(modules) + 2,
                "lessons": [
                    {
                        "title": "Project walkthrough",
                        "slug": f"{course['slug']}-project-walkthrough",
                        "summary": "Build the project step by step while naming each decision in plain language.",
                        "durationMinutes": 30,
                        "contentType": "project",
                    }
                ],
                "assessmentTitle": f"{title} project readiness quiz",
                "assessmentQuizId": f"{course['slug']}-project-readiness",
            },
        ])

    if not milestones:
        milestones.append({
            "title": f"{title} showcase project",
            "description": "Build a portfolio-ready deliverable that combines the most important course skills.",
            "milestoneOrder": 1,
            "estimatedHours": 8,
            "deliverables": [
                "Finished project source code",
                "Short explanation of design choices",
                "Screenshot or demo walkthrough",
            ],
            "completionThreshold": 80,
        })

    return {
        "courseSlug": course["slug"],
        "overview": f"{title} moves learners from guided foundations into practical implementation with project-based reinforcement. {instruction}".strip(),
        "modules": modules,
        "milestoneProjects": milestones,
        "sourceTags": tags,
    }


def _lesson_best_practices(category: str) -> list[str]:
    if category == "Backend Development":
        return [
            "Start from the request or data-flow problem before introducing implementation details.",
            "Use one end-to-end example so learners can trace input, processing, and output.",
            "Name tradeoffs early, then keep the first implementation deliberately small.",
        ]
    if category == "Systems Design":
        return [
            "Anchor the lesson in a real system constraint before naming patterns.",
            "Compare at least two reasonable options and explain why one is chosen first.",
            "Close with a scale or reliability question so learners practice making tradeoffs.",
        ]
    return [
        "Show the visual or interactive result before unpacking the code.",
        "Keep the first example intentionally small, then extend it once.",
        "Use guided edits so learners explain what changed and why it matters.",
    ]


def _build_lesson_content_plan_payload(course: dict, lesson: dict, instruction: str) -> dict:
    category = course.get("category", "Frontend Development")
    module_title = lesson.get("moduleTitle", "Module")
    lesson_title = lesson.get("title", "This lesson")
    summary = lesson.get("summary", "Explain the concept clearly and move into guided practice.")
    playground_mode = "web" if category == "Frontend Development" and lesson.get("contentType") != "quiz" else "javascript"

    return {
        "courseSlug": course["slug"],
        "lessonSlug": lesson["slug"],
        "moduleTitle": module_title,
        "lessonTitle": lesson_title,
        "instruction": instruction,
        "learnerPromise": f"By the end of {lesson_title}, the learner should explain the idea clearly and use it once with confidence.",
        "planningNotes": [
            f"Keep {lesson_title} tightly connected to the module promise in {module_title}.",
            f"Open with a practical {category.lower()} scenario before formal explanation.",
            "Use a demonstration, then a guided modification, then a short reflection question.",
        ],
        "sectionOutline": [
            "Why this lesson matters",
            "Mental model",
            "Guided example",
            "Practice task",
            "Common mistakes",
            "Reflection and next step",
        ],
        "recommendedObjectives": [
            f"Explain the core idea behind {lesson_title} in simple language.",
            "Use the concept in one guided implementation task.",
            "Identify one mistake or misconception to avoid.",
        ],
        "bestPractices": _lesson_best_practices(category),
        "practiceArc": [
            "Watch the worked example first.",
            "Change one important part deliberately.",
            "Explain the result before moving on.",
        ],
        "playgroundMode": playground_mode,
        "playgroundBrief": f"Give learners a small {category.lower()} task they can finish in one sitting without extra setup.",
        "summary": summary,
    }


def _build_generated_lesson_payload(course: dict, lesson: dict, plan_payload: dict) -> dict:
    module_title = plan_payload.get("moduleTitle", lesson.get("moduleTitle", "Module"))
    lesson_title = plan_payload.get("lessonTitle", lesson.get("title", "This lesson"))
    category = course.get("category", "Frontend Development")
    practice_arc = plan_payload.get("practiceArc", [])
    best_practices = plan_payload.get("bestPractices", [])
    recommended_objectives = plan_payload.get("recommendedObjectives", [])
    section_outline = plan_payload.get("sectionOutline", [])
    summary = plan_payload.get("summary") or lesson.get("summary", "Guide the learner through one clear concept.")
    playground_mode = plan_payload.get("playgroundMode", "web")

    markdown_sections = [
        f"# {lesson_title}",
        "",
        "## Why this lesson matters",
        summary,
        "",
        "## Mental model",
        f"Teach **{lesson_title}** as a practical move inside **{module_title}**. Start with the real task, then connect it to the underlying idea so the learner understands both the how and the why.",
        "",
        "## Guided walkthrough",
        f"Open with a small {category.lower()} example that works immediately. Narrate each decision, pause for prediction, then let the learner make one controlled change.",
        "",
        "## Teaching sequence",
    ]
    markdown_sections.extend([f"{index}. {item}" for index, item in enumerate(practice_arc or ["Explain the concept", "Model the implementation", "Guide one learner change"], start=1)])
    markdown_sections.extend(
        [
            "",
            "## Best-practice teaching notes",
            *[f"- {item}" for item in best_practices],
            "",
            "## Suggested lesson sections",
            *[f"- {item}" for item in section_outline],
            "",
            "## Common learner friction",
            "Learners may copy the pattern without understanding the decision behind it. Pause before each key step and ask what they expect to happen next.",
            "",
            "## Close the lesson",
            "End by connecting the concept back to the larger course outcome and ask the learner to describe when they would use this again.",
        ]
    )

    playground = None
    if lesson.get("contentType") not in {"quiz", "resource"}:
        if playground_mode == "web":
            playground = {
                "mode": "web",
                "instructions": f"Build a small interface that demonstrates {lesson_title.lower()}, then improve one part deliberately and explain the change.",
                "starterHtml": "<section class=\"lesson-demo\">\n  <h1>Lesson demo</h1>\n  <p>Start from this working example.</p>\n  <button id=\"lesson-action\">Try it</button>\n</section>",
                "starterCss": "body {\n  font-family: 'Segoe UI', sans-serif;\n  padding: 24px;\n  background: #f8fafc;\n}\n\n.lesson-demo {\n  max-width: 480px;\n  padding: 24px;\n  border-radius: 20px;\n  background: white;\n  box-shadow: 0 12px 28px rgba(15, 23, 42, 0.08);\n}\n",
                "starterJs": "const actionButton = document.getElementById('lesson-action');\n\nif (actionButton) {\n  actionButton.addEventListener('click', () => {\n    actionButton.textContent = 'Updated';\n  });\n}\n",
                "checks": [
                    {"label": "Use the lesson container", "type": "includes", "target": "html", "value": "lesson-demo"},
                    {"label": "Style the lesson container", "type": "includes", "target": "css", "value": ".lesson-demo"},
                    {"label": "Add lesson behavior", "type": "includes", "target": "js", "value": "addEventListener"},
                ],
            }
        else:
            playground = {
                "mode": "javascript",
                "instructions": f"Write a focused JavaScript example for {lesson_title.lower()} and print output that proves the logic works.",
                "starterJs": "function runLessonExample() {\n  return 'ready';\n}\n\nconsole.log(runLessonExample());\n",
                "checks": [
                    {"label": "Define a function", "type": "includes", "target": "js", "value": "function"},
                    {"label": "Log the result", "type": "includes", "target": "js", "value": "console.log"},
                ],
            }

    generated_lesson = normalize_lesson(
        course,
        module_title,
        {
            **lesson,
            "learningObjectives": recommended_objectives,
            "keyTakeaways": [
                summary,
                "Use the smallest useful example before layering more complexity.",
                "Pause to explain why the pattern works, not just how to type it.",
            ],
            "contentMarkdown": "\n".join(markdown_sections),
            "practicePrompt": (
                f"Create one small working example for **{lesson_title}**. Change one important part, then explain what changed and why the result is different."
            ),
            "instructorNotes": (
                "Generated with Deveda best-practice structure: concrete opening, guided example, learner modification, and reflective close."
            ),
            "playground": playground,
        },
    )
    return generated_lesson


def _build_course_content_plan_payload(course: dict, curriculum: Optional[dict], instruction: str) -> dict:
    base = curriculum or build_curriculum_scaffold(course)
    raw_modules = base.get("modules", [])
    milestone_projects = base.get("milestone_projects", base.get("milestoneProjects", []))
    module_target, _ = _course_target_counts(course)

    module_blueprints = []
    for index in range(1, max(len(raw_modules), module_target) + 1):
        module = raw_modules[index - 1] if index - 1 < len(raw_modules) else None
        planned_module = _merge_module_with_seed(course, {"modules": raw_modules}, module, index)
        lessons = planned_module.get("lessons", [])
        module_blueprints.append(
            {
                "title": planned_module.get("title", f"Module {index}"),
                "order": planned_module.get("order", index),
                "goal": planned_module.get("description", "Move learners through one coherent chunk of the course promise."),
                "lessonCount": len(lessons),
                "deliveryPattern": [
                    "Introduce the problem or use case.",
                    "Model the first implementation step by step.",
                    "Add a guided practice task before the checkpoint.",
                ],
                "lessonBlueprints": [
                    {
                        "title": lesson.get("title", f"Lesson {lesson_index}"),
                        "goal": lesson.get("summary", "Clarify the concept and connect it to practice."),
                    }
                    for lesson_index, lesson in enumerate(lessons, start=1)
                ],
            }
        )

    return {
        "courseSlug": course["slug"],
        "courseTitle": course["title"],
        "instruction": instruction,
        "backgroundAgents": [
            "Curriculum planner maps module order, checkpoints, and milestone pacing.",
            "Lesson designer expands each lesson into explanation, practice, and reflection.",
            "Practice designer adds runnable tasks and instructor coaching notes.",
        ],
        "planningNotes": [
            f"Keep {course['title']} centered on one visible learner outcome.",
            "Use short modules with clear assessment moments rather than long undifferentiated content blocks.",
            "Every lesson should move through explanation, demonstration, guided practice, and reflection.",
        ],
        "moduleBlueprints": module_blueprints,
        "milestoneStrategy": [
            project.get("title", "Milestone project")
            for project in milestone_projects
        ]
        or [f"{course['title']} capstone"],
    }


def _course_target_counts(course: dict) -> tuple[int, int]:
    total_lessons = int(course.get("total_lessons", course.get("totalLessons", 0)) or 0)
    total_lessons = max(total_lessons, 8)
    if total_lessons <= 12:
        return 4, total_lessons
    if total_lessons <= 18:
        return 5, total_lessons
    return 6, total_lessons


def _coerce_string_list(value: Any, fallback: list[str]) -> list[str]:
    if isinstance(value, list):
        cleaned = [str(item).strip() for item in value if str(item).strip()]
        if cleaned:
            return cleaned
    return fallback


def _fallback_course_theme_pool(course: dict) -> list[dict]:
    category = course.get("category", "Frontend Development")
    if category == "Backend Development":
        return [
            {
                "title": "Python setup and backend workflow",
                "focus": "Build the Python habits and project structure needed for backend work.",
                "lessons": [
                    {"title": "Set up a Python service project", "summary": "Create the first backend workspace and explain how files, dependencies, and commands fit together."},
                    {"title": "Run a local development loop", "summary": "Start, stop, and inspect a local service so learners understand the development workflow."},
                    {"title": "Read requests and logs", "summary": "Use terminal output and request traces to understand what the service is doing."},
                ],
            },
            {
                "title": "HTTP requests and API design",
                "focus": "Understand requests, responses, routes, and resource design.",
                "lessons": [
                    {"title": "Understand the request-response cycle", "summary": "Explain how a client talks to a server and what each HTTP response communicates."},
                    {"title": "Design clear API routes", "summary": "Choose route names and resource patterns that stay readable as the service grows."},
                    {"title": "Return useful API responses", "summary": "Shape status codes and response bodies so clients can handle outcomes correctly."},
                ],
            },
            {
                "title": "Validation and service logic",
                "focus": "Turn inputs into useful responses with clean validation and error handling.",
                "lessons": [
                    {"title": "Validate incoming data", "summary": "Check user input before it reaches business logic and explain why that protects the service."},
                    {"title": "Write clear service functions", "summary": "Move logic out of routes so the code stays testable and easier to reason about."},
                    {"title": "Handle errors without confusion", "summary": "Return predictable error messages and teach learners how to diagnose failures."},
                ],
            },
            {
                "title": "Persistence and testing basics",
                "focus": "Store data, test the service, and debug with confidence.",
                "lessons": [
                    {"title": "Connect the service to stored data", "summary": "Save and retrieve records while keeping the data flow easy to follow."},
                    {"title": "Write backend tests that prove behavior", "summary": "Use small tests to confirm routes and service logic work as expected."},
                    {"title": "Debug failing API behavior", "summary": "Trace failures back to code, data, or request shape and fix them methodically."},
                ],
            },
            {
                "title": "Authentication and production habits",
                "focus": "Protect the service and prepare it for realistic use.",
                "lessons": [
                    {"title": "Add authentication to protected routes", "summary": "Introduce basic auth flow and explain when endpoints should require identity."},
                    {"title": "Manage configuration safely", "summary": "Use environment settings without leaking secrets or breaking deployments."},
                    {"title": "Prepare an API for deployment", "summary": "Review logging, validation, and runtime checks before shipping the service."},
                ],
            },
            {
                "title": "Capstone API implementation",
                "focus": "Ship a meaningful backend feature from plan to delivery.",
                "lessons": [
                    {"title": "Plan the capstone API", "summary": "Break one useful backend feature into routes, data, validation, and tests."},
                    {"title": "Build the capstone endpoints", "summary": "Implement the main feature in small steps while explaining each backend decision."},
                    {"title": "Review and harden the capstone", "summary": "Test, debug, and improve the final API so it feels production-aware."},
                ],
            },
        ]
    if category == "Systems Design":
        return [
            {
                "title": "Requirements and system boundaries",
                "focus": "Learn how to turn product requirements into architectural questions.",
                "lessons": [
                    {"title": "Clarify functional requirements", "summary": "Separate what the system must do from assumptions that need validation."},
                    {"title": "Define scope and boundaries", "summary": "Identify users, interfaces, and constraints before proposing architecture."},
                    {"title": "Turn product goals into design questions", "summary": "Translate vague requirements into concrete system design decisions."},
                ],
            },
            {
                "title": "Traffic, scale, and data flow",
                "focus": "Understand how systems behave as load grows.",
                "lessons": [
                    {"title": "Estimate scale with back-of-the-envelope math", "summary": "Use rough calculations to reason about load before picking components."},
                    {"title": "Map end-to-end request flow", "summary": "Trace how data moves through a system and where bottlenecks can appear."},
                    {"title": "Plan for traffic spikes", "summary": "Choose scaling approaches that match the system's workload pattern."},
                ],
            },
            {
                "title": "Storage and consistency tradeoffs",
                "focus": "Compare data choices and retrieval strategies.",
                "lessons": [
                    {"title": "Choose the right storage model", "summary": "Compare relational, document, and key-value choices for different data needs."},
                    {"title": "Design read and write paths", "summary": "Explain how data access patterns shape the architecture."},
                    {"title": "Reason about consistency tradeoffs", "summary": "Teach when to prefer stronger guarantees or more flexible scaling."},
                ],
            },
            {
                "title": "Reliability and operations",
                "focus": "Plan for failures, monitoring, and resilient delivery.",
                "lessons": [
                    {"title": "Design for failure recovery", "summary": "Identify likely failure modes and add practical mitigation strategies."},
                    {"title": "Use monitoring and alerting well", "summary": "Explain which signals help teams understand production health."},
                    {"title": "Improve resilience step by step", "summary": "Prioritize redundancy, retries, and graceful degradation without overengineering."},
                ],
            },
            {
                "title": "Communicating architecture decisions",
                "focus": "Practice clear communication and tradeoff analysis.",
                "lessons": [
                    {"title": "Present an architecture clearly", "summary": "Structure a design explanation so listeners can follow the reasoning quickly."},
                    {"title": "Defend tradeoffs under questions", "summary": "Respond to challenges by comparing alternatives instead of hand-waving."},
                    {"title": "Summarize the design concisely", "summary": "Close with the most important choices, risks, and next steps."},
                ],
            },
            {
                "title": "Capstone system design case",
                "focus": "Present one end-to-end system design with reasoning.",
                "lessons": [
                    {"title": "Frame the capstone scenario", "summary": "Break a realistic product prompt into requirements, scale, and constraints."},
                    {"title": "Draft the end-to-end architecture", "summary": "Connect major components into one coherent system design."},
                    {"title": "Review tradeoffs and risks", "summary": "Refine the final design by naming weak points and practical improvements."},
                ],
            },
        ]
    return [
        {
            "title": "HTML foundations and page structure",
            "focus": "Start with semantic structure and the mental model of a web page.",
            "lessons": [
                {"title": "Understand how a web page is structured", "summary": "Explain how browsers read HTML and why semantic structure matters from the start."},
                {"title": "Build clear page sections with semantic HTML", "summary": "Use headings, sections, lists, and landmarks to create readable page structure."},
                {"title": "Create a simple profile page", "summary": "Apply semantic HTML in a small page that already looks like a real interface."},
            ],
        },
        {
            "title": "CSS styling and layout",
            "focus": "Turn plain markup into intentional interfaces with layout and typography.",
            "lessons": [
                {"title": "Style text, color, and spacing with CSS", "summary": "Use core CSS properties to make a page feel organized and readable."},
                {"title": "Build layouts with flexbox and grid", "summary": "Position content intentionally instead of relying on default document flow."},
                {"title": "Create a polished card layout", "summary": "Combine spacing, typography, and layout rules in one reusable interface block."},
            ],
        },
        {
            "title": "JavaScript interactivity",
            "focus": "Add behavior with JavaScript, the DOM, and event handling.",
            "lessons": [
                {"title": "Read and change the DOM with JavaScript", "summary": "Use selectors and property updates to control what the learner sees in the browser."},
                {"title": "Respond to clicks and form input", "summary": "Handle events so the page reacts to user behavior in clear, predictable ways."},
                {"title": "Build an interactive message component", "summary": "Combine DOM updates and events in a small feature that feels useful."},
            ],
        },
        {
            "title": "Responsive project build",
            "focus": "Combine structure, styling, and interactivity in one guided project.",
            "lessons": [
                {"title": "Plan a small responsive page", "summary": "Break a practical frontend project into sections, styles, and interactions before coding."},
                {"title": "Build the first responsive section", "summary": "Implement a layout that adapts cleanly across screen sizes."},
                {"title": "Add interaction and polish to the project", "summary": "Finish the guided build with small behaviors and visual refinement."},
            ],
        },
        {
            "title": "Reusable UI patterns",
            "focus": "Introduce components, consistency, and extension work.",
            "lessons": [
                {"title": "Turn repeated markup into reusable patterns", "summary": "Identify repeated UI pieces and rebuild them with consistency in mind."},
                {"title": "Create a small component library mindset", "summary": "Use naming, spacing, and class structure that scales beyond one page."},
                {"title": "Extend a design without breaking consistency", "summary": "Add a new feature while preserving the visual and structural rules already in place."},
            ],
        },
        {
            "title": "Accessibility and performance basics",
            "focus": "Improve the build with responsible frontend habits.",
            "lessons": [
                {"title": "Make interface content easier to access", "summary": "Improve headings, labels, contrast, and interaction flow for more learners and users."},
                {"title": "Reduce avoidable frontend performance issues", "summary": "Teach the habits that keep pages responsive without introducing premature complexity."},
                {"title": "Review and improve the final frontend build", "summary": "Run a quality pass that strengthens usability, accessibility, and responsiveness together."},
            ],
        },
    ]


def _is_generic_title(title: str) -> bool:
    normalized = _normalize_text(title)
    generic_phrases = {
        "foundation sprint",
        "orientation",
        "introduction",
        "intro",
        "module 1",
        "module 2",
        "module 3",
        "first guided implementation",
        "lesson 1",
        "lesson 2",
        "lesson 3",
    }
    return (
        normalized in generic_phrases
        or normalized.startswith("module ")
        or normalized.startswith("lesson ")
        or normalized.endswith(" orientation")
        or normalized.startswith("introduction to ")
        or "guided implementation" in normalized
    )


def _is_scaffold_origin(item: dict) -> bool:
    return str(item.get("source", "")).strip().lower() == "scaffold"


def _fallback_theme_for_module(course: dict, module_order: int) -> dict:
    themes = _fallback_course_theme_pool(course)
    return themes[min(module_order - 1, len(themes) - 1)]


def _authoritative_modules(curriculum: Optional[dict], *, exclude_order: Optional[int] = None) -> list[dict]:
    if not curriculum:
        return []

    modules = curriculum.get("modules", [])
    authoritative = []
    for module in modules:
        module_order = int(module.get("order", 0) or 0)
        if exclude_order and module_order == exclude_order:
            continue
        if _is_scaffold_origin(module) or _is_generic_title(str(module.get("title", ""))):
            continue
        authoritative.append(
            {
                "title": module.get("title"),
                "description": module.get("description"),
                "order": module_order,
                "assessmentTitle": module.get("assessmentTitle"),
                "lessons": [
                    {
                        "title": lesson.get("title"),
                        "summary": lesson.get("summary"),
                        "source": lesson.get("source", "manual"),
                    }
                    for lesson in module.get("lessons", [])
                    if not _is_scaffold_origin(lesson) and not _is_generic_title(str(lesson.get("title", "")))
                ],
            }
        )
    return authoritative


def _module_generation_seed(course: dict, curriculum: dict, module_order: int) -> dict:
    modules = curriculum.get("modules", [])
    existing = modules[module_order - 1] if 0 <= module_order - 1 < len(modules) else {}
    if existing and not _is_scaffold_origin(existing) and not _is_generic_title(str(existing.get("title", ""))):
        return {
            "title": existing.get("title"),
            "description": existing.get("description"),
            "order": existing.get("order", module_order),
            "assessmentTitle": existing.get("assessmentTitle"),
            "assessmentQuizId": existing.get("assessmentQuizId"),
            "lessons": [
                {
                    "title": lesson.get("title"),
                    "slug": lesson.get("slug"),
                    "summary": lesson.get("summary"),
                    "durationMinutes": lesson.get("durationMinutes"),
                    "contentType": lesson.get("contentType"),
                }
                for lesson in existing.get("lessons", [])
            ],
        }

    fallback_theme = _fallback_theme_for_module(course, module_order)
    lesson_seeds = fallback_theme.get("lessons", [])
    return {
        "title": fallback_theme["title"],
        "description": fallback_theme["focus"],
        "order": module_order,
        "assessmentTitle": f"{fallback_theme['title']} applied checkpoint",
        "assessmentQuizId": f"{course['slug']}-module-{module_order}-applied-check",
        "lessons": [
            {
                "title": lesson_seed.get("title", f"{fallback_theme['title']} lesson {index}"),
                "slug": _slugify_title(
                    f"{course['slug']}-{lesson_seed.get('title') or (fallback_theme['title'] + f' lesson {index}')}"
                ),
                "summary": lesson_seed.get("summary", fallback_theme["focus"]),
                "durationMinutes": 20,
                "contentType": "lesson",
            }
            for index, lesson_seed in enumerate(lesson_seeds, start=1)
        ],
    }


def _merge_module_with_seed(course: dict, curriculum: Optional[dict], module: Optional[dict], module_order: int) -> dict:
    candidate = module if isinstance(module, dict) else {}
    seed = _module_generation_seed(course, curriculum or {}, module_order)
    seed_lessons = seed.get("lessons", []) if isinstance(seed.get("lessons"), list) else []
    candidate_lessons = candidate.get("lessons", []) if isinstance(candidate.get("lessons"), list) else []

    merged_lessons = []
    total_lessons = max(len(candidate_lessons), len(seed_lessons), 1)
    for lesson_index in range(total_lessons):
        seed_lesson = seed_lessons[lesson_index] if lesson_index < len(seed_lessons) else {
            "title": f"{seed['title']} lesson {lesson_index + 1}",
            "slug": _slugify_title(f"{course['slug']}-{seed['title']}-lesson-{lesson_index + 1}"),
            "summary": seed.get("description", ""),
            "durationMinutes": 20,
            "contentType": "lesson",
        }
        candidate_lesson = candidate_lessons[lesson_index] if lesson_index < len(candidate_lessons) else {}
        lesson_title = str(candidate_lesson.get("title", "")).strip()
        merged_lessons.append(
            {
                **seed_lesson,
                **candidate_lesson,
                "title": lesson_title if lesson_title and not _is_generic_title(lesson_title) else seed_lesson.get("title"),
                "slug": str(candidate_lesson.get("slug", "")).strip() or seed_lesson.get("slug"),
                "summary": str(candidate_lesson.get("summary", "")).strip() or seed_lesson.get("summary"),
                "durationMinutes": max(int(candidate_lesson.get("durationMinutes", seed_lesson.get("durationMinutes", 20)) or 20), 10),
                "contentType": str(candidate_lesson.get("contentType", seed_lesson.get("contentType", "lesson"))).strip() or "lesson",
            }
        )

    candidate_title = str(candidate.get("title", "")).strip()
    return {
        **seed,
        **candidate,
        "title": candidate_title if candidate_title and not _is_generic_title(candidate_title) else seed.get("title"),
        "description": str(candidate.get("description", "")).strip() or seed.get("description"),
        "order": max(int(candidate.get("order", seed.get("order", module_order)) or module_order), 1),
        "assessmentTitle": str(candidate.get("assessmentTitle", "")).strip() or seed.get("assessmentTitle"),
        "assessmentQuizId": str(candidate.get("assessmentQuizId", "")).strip() or seed.get("assessmentQuizId"),
        "lessons": merged_lessons,
    }


def _normalize_generated_curriculum_payload(course: dict, payload: dict) -> Optional[dict]:
    modules = payload.get("modules", [])
    if not isinstance(modules, list) or not modules:
        return None

    normalized_modules = []
    for module_index, module in enumerate(modules, start=1):
        module_title = str(module.get("title", f"Module {module_index}")).strip() or f"Module {module_index}"
        lessons = module.get("lessons", []) if isinstance(module.get("lessons"), list) else []
        normalized_lessons = []

        for lesson_index, lesson in enumerate(lessons, start=1):
            lesson_title = str(lesson.get("title", f"{module_title} lesson {lesson_index}")).strip() or f"{module_title} lesson {lesson_index}"
            lesson_context = {
                "title": lesson_title,
                "slug": str(lesson.get("slug", _slugify_title(f"{course['slug']}-{lesson_title}"))).strip() or _slugify_title(f"{course['slug']}-{lesson_title}"),
                "summary": str(lesson.get("summary", f"Apply the main idea in {lesson_title} through guided practice.")).strip(),
                "durationMinutes": max(int(lesson.get("durationMinutes", 20) or 20), 10),
                "contentType": str(lesson.get("contentType", "lesson")).strip() or "lesson",
                "quizId": lesson.get("quizId"),
                "quizTitle": lesson.get("quizTitle"),
                "learningObjectives": _coerce_string_list(lesson.get("learningObjectives"), [
                    f"Explain the core idea behind {lesson_title} in simple language.",
                    "Use the concept in one guided implementation task.",
                    "Identify one mistake or misconception to avoid.",
                ]),
                "keyTakeaways": _coerce_string_list(lesson.get("keyTakeaways"), [
                    str(lesson.get("summary", f"Understand how {lesson_title} works in practice.")).strip(),
                    "Use a small working example before layering more complexity.",
                    "Connect the technique back to the larger course outcome.",
                ]),
                "contentMarkdown": str(lesson.get("contentMarkdown", "")).strip(),
                "practicePrompt": str(lesson.get("practicePrompt", "")).strip(),
                "instructorNotes": str(lesson.get("instructorNotes", "")).strip(),
                "playground": lesson.get("playground") if isinstance(lesson.get("playground"), dict) else None,
                "moduleTitle": module_title,
            }
            has_explicit_content = any(
                [
                    lesson_context["contentMarkdown"],
                    lesson_context["practicePrompt"],
                    lesson_context["instructorNotes"],
                    bool(lesson_context["playground"]),
                ]
            )
            if has_explicit_content:
                normalized_lessons.append(
                    normalize_lesson(
                        course,
                        module_title,
                        {
                            **lesson_context,
                            "learningObjectives": lesson_context["learningObjectives"],
                            "keyTakeaways": lesson_context["keyTakeaways"],
                            "contentMarkdown": lesson_context["contentMarkdown"],
                            "practicePrompt": lesson_context["practicePrompt"],
                            "instructorNotes": lesson_context["instructorNotes"],
                            "playground": lesson_context["playground"],
                        },
                    )
                )
            else:
                lesson_plan = _build_lesson_content_plan_payload(course, lesson_context, f"Build complete lesson content for {lesson_title}.")
                normalized_lessons.append(_build_generated_lesson_payload(course, lesson_context, lesson_plan))

        normalized_modules.append(
            {
                "title": module_title,
                "description": str(module.get("description", f"Guide learners through {module_title.lower()} with practical repetition and a clear checkpoint.")).strip(),
                "order": max(int(module.get("order", module_index) or module_index), 1),
                "lessons": normalized_lessons,
                "assessmentTitle": str(module.get("assessmentTitle", f"{module_title} applied checkpoint")).strip() or f"{module_title} applied checkpoint",
                "assessmentQuizId": str(module.get("assessmentQuizId", f"{course['slug']}-module-{module_index}-applied-check")).strip() or f"{course['slug']}-module-{module_index}-applied-check",
            }
        )

    return {
        "courseSlug": course["slug"],
        "overview": str(payload.get("overview", "")).strip() or f"{course['title']} moves learners from guided foundations into practical delivery through concise modules and milestone work.",
        "modules": normalized_modules,
        "milestoneProjects": _normalize_generated_milestones(course, payload.get("milestoneProjects", payload.get("milestone_projects", []))),
    }


def _normalize_generated_module_payload(course: dict, module: dict, module_index: int) -> dict:
    module_title = str(module.get("title", f"Module {module_index}")).strip() or f"Module {module_index}"
    lessons = module.get("lessons", []) if isinstance(module.get("lessons"), list) else []
    normalized_lessons = []

    for lesson_index, lesson in enumerate(lessons, start=1):
        lesson_title = str(lesson.get("title", f"{module_title} lesson {lesson_index}")).strip() or f"{module_title} lesson {lesson_index}"
        lesson_context = {
            "title": lesson_title,
            "slug": str(lesson.get("slug", _slugify_title(f"{course['slug']}-{lesson_title}"))).strip() or _slugify_title(f"{course['slug']}-{lesson_title}"),
            "source": "agent",
            "summary": str(lesson.get("summary", f"Apply the main idea in {lesson_title} through guided practice.")).strip(),
            "durationMinutes": max(int(lesson.get("durationMinutes", 20) or 20), 10),
            "contentType": str(lesson.get("contentType", "lesson")).strip() or "lesson",
            "quizId": lesson.get("quizId"),
            "quizTitle": lesson.get("quizTitle"),
            "learningObjectives": _coerce_string_list(lesson.get("learningObjectives"), [
                f"Explain the core idea behind {lesson_title} in simple language.",
                "Use the concept in one guided implementation task.",
                "Identify one mistake or misconception to avoid.",
            ]),
            "keyTakeaways": _coerce_string_list(lesson.get("keyTakeaways"), [
                str(lesson.get("summary", f"Understand how {lesson_title} works in practice.")).strip(),
                "Use a small working example before layering more complexity.",
                "Connect the technique back to the larger course outcome.",
            ]),
            "contentMarkdown": str(lesson.get("contentMarkdown", "")).strip(),
            "practicePrompt": str(lesson.get("practicePrompt", "")).strip(),
            "instructorNotes": str(lesson.get("instructorNotes", "")).strip(),
            "playground": lesson.get("playground") if isinstance(lesson.get("playground"), dict) else None,
            "moduleTitle": module_title,
        }
        has_explicit_content = any(
            [
                lesson_context["contentMarkdown"],
                lesson_context["practicePrompt"],
                lesson_context["instructorNotes"],
                bool(lesson_context["playground"]),
            ]
        )
        if has_explicit_content:
            normalized_lessons.append(
                normalize_lesson(
                    course,
                    module_title,
                    {
                        **lesson_context,
                        "learningObjectives": lesson_context["learningObjectives"],
                        "keyTakeaways": lesson_context["keyTakeaways"],
                        "contentMarkdown": lesson_context["contentMarkdown"],
                        "practicePrompt": lesson_context["practicePrompt"],
                        "instructorNotes": lesson_context["instructorNotes"],
                        "playground": lesson_context["playground"],
                    },
                )
            )
        else:
            lesson_plan = _build_lesson_content_plan_payload(course, lesson_context, f"Build complete lesson content for {lesson_title}.")
            normalized_lessons.append(_build_generated_lesson_payload(course, lesson_context, lesson_plan))

    if not normalized_lessons:
        fallback_lesson = {
            "title": f"{module_title} foundations",
            "slug": _slugify_title(f"{course['slug']}-{module_title}-foundations"),
            "source": "agent",
            "summary": f"Introduce the most important idea in {module_title}.",
            "durationMinutes": 20,
            "contentType": "lesson",
            "moduleTitle": module_title,
        }
        lesson_plan = _build_lesson_content_plan_payload(course, fallback_lesson, f"Build complete lesson content for {module_title}.")
        normalized_lessons.append(_build_generated_lesson_payload(course, fallback_lesson, lesson_plan))

    return {
        "title": module_title,
        "description": str(module.get("description", f"Guide learners through {module_title.lower()} with practical repetition and a clear checkpoint.")).strip(),
        "order": max(int(module.get("order", module_index) or module_index), 1),
        "source": "agent",
        "lessons": normalized_lessons,
        "assessmentTitle": str(module.get("assessmentTitle", f"{module_title} applied checkpoint")).strip() or f"{module_title} applied checkpoint",
        "assessmentQuizId": str(module.get("assessmentQuizId", f"{course['slug']}-module-{module_index}-applied-check")).strip() or f"{course['slug']}-module-{module_index}-applied-check",
    }


def _normalize_generated_outline_module(course: dict, module: dict, module_index: int) -> dict:
    module_title = str(module.get("title", f"Module {module_index}")).strip() or f"Module {module_index}"
    lessons = module.get("lessons", []) if isinstance(module.get("lessons"), list) else []
    normalized_lessons = []

    for lesson_index, lesson in enumerate(lessons, start=1):
        lesson_title = str(lesson.get("title", f"{module_title} lesson {lesson_index}")).strip() or f"{module_title} lesson {lesson_index}"
        normalized_lessons.append(
            {
                "title": lesson_title,
                "slug": str(lesson.get("slug", _slugify_title(f"{course['slug']}-{lesson_title}"))).strip()
                or _slugify_title(f"{course['slug']}-{lesson_title}"),
                "source": "agent",
                "summary": str(lesson.get("summary", f"Apply the main idea in {lesson_title} through guided practice.")).strip(),
                "durationMinutes": max(int(lesson.get("durationMinutes", 20) or 20), 10),
                "contentType": str(lesson.get("contentType", "lesson")).strip() or "lesson",
                "quizId": lesson.get("quizId"),
                "quizTitle": lesson.get("quizTitle"),
            }
        )

    if not normalized_lessons:
        normalized_lessons = [
            {
                "title": f"{module_title} lesson",
                "slug": _slugify_title(f"{course['slug']}-{module_title}-lesson"),
                "source": "agent",
                "summary": f"Introduce the core idea in {module_title} with one clear example and a guided task.",
                "durationMinutes": 20,
                "contentType": "lesson",
                "quizId": None,
                "quizTitle": None,
            }
        ]

    return {
        "title": module_title,
        "description": str(module.get("description", f"Guide learners through {module_title.lower()} with clear examples and one checkpoint.")).strip(),
        "order": max(int(module.get("order", module_index) or module_index), 1),
        "source": "agent",
        "lessons": normalized_lessons,
        "assessmentTitle": str(module.get("assessmentTitle", f"{module_title} applied checkpoint")).strip() or f"{module_title} applied checkpoint",
        "assessmentQuizId": str(module.get("assessmentQuizId", f"{course['slug']}-module-{module_index}-applied-check")).strip() or f"{course['slug']}-module-{module_index}-applied-check",
    }


def _normalize_generated_course_outline_payload(course: dict, payload: dict, curriculum: Optional[dict] = None) -> Optional[dict]:
    modules = payload.get("modules", [])
    if not isinstance(modules, list) or not modules:
        return None

    normalized_modules = []
    for module_index, module in enumerate(modules, start=1):
        merged_module = _merge_module_with_seed(course, curriculum, module, module_index)
        normalized_modules.append(_normalize_generated_outline_module(course, merged_module, module_index))

    return {
        "courseSlug": course["slug"],
        "overview": str(payload.get("overview", "")).strip() or f"{course['title']} moves learners through short, practical modules that build one visible skill at a time.",
        "modules": normalized_modules,
        "milestoneProjects": _normalize_generated_milestones(course, payload.get("milestoneProjects", payload.get("milestone_projects", []))),
    }


def _normalize_generated_milestones(course: dict, projects: Any) -> list[dict]:
    normalized_projects = []
    if isinstance(projects, list):
        for project_index, project in enumerate(projects, start=1):
            normalized_projects.append(
                {
                    "title": str(project.get("title", f"{course['title']} milestone {project_index}")).strip() or f"{course['title']} milestone {project_index}",
                    "description": str(project.get("description", "Build a practical project that proves the learner can use the module skills together.")).strip(),
                    "milestoneOrder": max(int(project.get("milestoneOrder", project_index) or project_index), 1),
                    "estimatedHours": max(int(project.get("estimatedHours", 6) or 6), 1),
                    "deliverables": _coerce_string_list(project.get("deliverables"), ["Working implementation", "README or explanation", "Demo notes"]),
                    "completionThreshold": max(min(int(project.get("completionThreshold", 80) or 80), 100), 50),
                }
            )

    return normalized_projects or [
        {
            "title": f"{course['title']} capstone project",
            "description": "Build an end-to-end deliverable that combines the course skills in one coherent result.",
            "milestoneOrder": 1,
            "estimatedHours": 8,
            "deliverables": ["Working implementation", "README or explanation", "Demo notes"],
            "completionThreshold": 80,
        }
    ]


def _openai_json_request(messages: list[dict], timeout: int = 30) -> Optional[dict]:
    try:
        result = AgentGraphRuntime.invoke_json_response_sync(messages, timeout=timeout, temperature=0.4)
        if result is not None:
            return result
    except Exception:
        pass

    if not OPENAI_API_KEY:
        return None

    payload = {
        "model": OPENAI_MODEL,
        "messages": messages,
        "temperature": 0.4,
        "response_format": {"type": "json_object"},
    }
    req = request.Request(
        "https://api.openai.com/v1/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {OPENAI_API_KEY}",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    try:
        with request.urlopen(req, timeout=timeout) as response:
            body = json.loads(response.read().decode("utf-8"))
            return json.loads(body["choices"][0]["message"]["content"])
    except (TimeoutError, socket.timeout, error.HTTPError, error.URLError, KeyError, IndexError, json.JSONDecodeError, TypeError, ValueError, OSError):
        return None


def _generate_course_payload_with_openai(
    course: dict,
    curriculum: Optional[dict],
    instruction: str,
    plan_payload: Optional[dict] = None,
) -> Optional[dict]:
    if not OPENAI_API_KEY:
        return None

    module_target, lesson_target = _course_target_counts(course)
    total_quizzes = int(course.get("total_quizzes", course.get("totalQuizzes", 0)) or 0)
    course_context = {
        "title": course.get("title"),
        "slug": course.get("slug"),
        "description": course.get("description"),
        "category": course.get("category"),
        "difficulty": course.get("difficulty"),
        "durationMinutes": course.get("duration", 0),
        "totalLessons": course.get("total_lessons", course.get("totalLessons", 0)),
        "totalQuizzes": total_quizzes,
        "tags": course.get("tags", []),
        "prerequisites": course.get("prerequisites", []),
        "existingAuthoritativeModules": _authoritative_modules(curriculum),
        "moduleThemeHints": _fallback_course_theme_pool(course)[:module_target],
        "plan": plan_payload or {},
        "instruction": instruction,
        "targets": {
            "modules": module_target,
            "lessons": lesson_target,
            "quizzes": max(total_quizzes, module_target),
        },
    }
    structure = _openai_json_request(
        [
            {
                "role": "system",
                "content": (
                    "You are Deveda's curriculum generation engine. Return valid JSON only. "
                    "First create the course structure only: concise overview, module titles, module descriptions, lesson blueprints, and milestone projects. "
                    "Avoid generic placeholder names. Treat scaffold/default module names as invalid. "
                    "Write concrete module and lesson titles that teach the actual subject matter."
                ),
            },
            {
                "role": "user",
                "content": (
                    "Create JSON with this exact top-level shape: "
                    "{\"overview\": string, \"modules\": [{\"title\": string, \"description\": string, \"order\": number, "
                    "\"assessmentTitle\": string, "
                    "\"lessons\": [{\"title\": string, \"slug\": string, \"summary\": string, \"durationMinutes\": number, \"contentType\": string}]}], "
                    "\"milestoneProjects\": [{\"title\": string, \"description\": string, \"milestoneOrder\": number, "
                    "\"estimatedHours\": number, \"deliverables\": string[], \"completionThreshold\": number}]}. "
                    f"Course context: {json.dumps(course_context, default=str)}"
                ),
            },
        ],
        timeout=28,
    )
    if not structure:
        return None
    return _normalize_generated_course_outline_payload(course, structure, curriculum)


def _generate_course_payload_fallback(course: dict, instruction: str) -> dict:
    module_target, lesson_target = _course_target_counts(course)
    themes = _fallback_course_theme_pool(course)[:module_target]
    duration_per_lesson = max(round(int(course.get("duration", 240) or 240) / max(lesson_target, 1)), 15)

    generated_modules = []
    for module_index, theme in enumerate(themes, start=1):
        module_title = theme["title"]
        generated_lessons = []
        lesson_seeds = theme.get("lessons", []) or [
            {
                "title": f"{module_title} lesson",
                "summary": f"{theme['focus']} This lesson moves the learner one clear step forward.",
            }
        ]
        for lesson_index, lesson_seed in enumerate(lesson_seeds, start=1):
            lesson_title = lesson_seed.get("title", f"{module_title} lesson {lesson_index}")
            generated_lessons.append(
                {
                    "title": lesson_title,
                    "slug": _slugify_title(f"{course['slug']}-{lesson_title}"),
                    "source": "agent",
                    "summary": lesson_seed.get("summary", f"{theme['focus']} This lesson moves the learner one clear step forward."),
                    "durationMinutes": duration_per_lesson,
                    "contentType": "lesson",
                    "quizId": None,
                    "quizTitle": None,
                }
            )

        generated_modules.append(
            {
                "title": module_title,
                "description": theme["focus"],
                "order": module_index,
                "source": "agent",
                "lessons": generated_lessons,
                "assessmentTitle": f"{module_title} applied checkpoint",
                "assessmentQuizId": f"{course['slug']}-module-{module_index}-applied-check",
            }
        )

    return {
        "courseSlug": course["slug"],
        "overview": (
            f"{course['title']} helps learners progress through {course.get('description', '').strip()} "
            "The curriculum stays concise and project-driven: each module explains the concept, demonstrates it, gives learners a guided task, and closes with a checkpoint."
        ).strip(),
        "modules": generated_modules,
        "milestoneProjects": [
            {
                "title": f"{course['title']} guided capstone",
                "description": "Create a practical final build that combines the most important lessons from the course into one portfolio-ready result.",
                "milestoneOrder": 1,
                "estimatedHours": 8 if course.get("difficulty") in {"Advanced", "Mastery"} else 6,
                "deliverables": [
                    "Working implementation",
                    "README with setup and usage notes",
                    "Short reflection on key decisions and tradeoffs",
                ],
                "completionThreshold": 80,
            }
        ],
    }


def _build_generated_course_payload(course: dict, curriculum: Optional[dict], instruction: str, plan_payload: Optional[dict] = None) -> dict:
    generated_curriculum = _generate_course_payload_with_openai(course, curriculum, instruction, plan_payload=plan_payload) or _generate_course_payload_fallback(
        course,
        instruction,
    )
    return {
        "courseSlug": course["slug"],
        "instruction": instruction,
        "planningNotes": (plan_payload or {}).get("planningNotes", []),
        "courseContext": {
            "title": course.get("title"),
            "description": course.get("description"),
            "category": course.get("category"),
            "difficulty": course.get("difficulty"),
            "tags": course.get("tags", []),
            "prerequisites": course.get("prerequisites", []),
            "duration": course.get("duration", 0),
            "totalLessons": course.get("total_lessons", course.get("totalLessons", 0)),
            "totalQuizzes": course.get("total_quizzes", course.get("totalQuizzes", 0)),
        },
        "curriculum": generated_curriculum,
    }


def _progress_analyst_reply(message: str, context: dict) -> str:
    learner = context.get("learner")
    summary = context.get("summary", {})
    courses = context.get("courses", [])
    quizzes = context.get("quizzes", [])

    if not learner:
        return (
            "I need a target learner before I can analyze progress. Request this agent with a student attached, then I can summarize strengths, friction points, and lesson plan changes."
        )

    weak_courses = [course for course in courses if course.get("progress", 0) < 40][:2]
    strong_courses = [course for course in courses if course.get("progress", 0) >= 70][:2]
    latest_quiz = quizzes[0] if quizzes else None

    lines = [
        f"Learner snapshot for {learner['firstName']} {learner['lastName']}: average course progress is {summary.get('averageProgress', 0)}% and quiz pass rate is {summary.get('passRate', 0)}%.",
    ]

    if strong_courses:
        lines.append(
            "Strength signal: the learner is moving well in "
            + ", ".join(course.get("course_slug", "a course") for course in strong_courses)
            + "."
        )
    if weak_courses:
        lines.append(
            "Friction signal: they may need more scaffolding in "
            + ", ".join(course.get("course_slug", "a course") for course in weak_courses)
            + "."
        )
    if latest_quiz:
        lines.append(
            f"Most recent quiz result: {latest_quiz.get('quiz_id')} at {latest_quiz.get('score', 0)}%."
        )

    lines.append(
        "Planning move: keep the next lesson short, concrete, and example-heavy. Start with a worked example, then ask the learner to modify one part instead of building from zero."
    )
    lines.append(
        "If confidence seems low, use a story-based explanation first: 'Imagine the app is a kitchen and each function is a station with one job.' Then map the story back to the code."
    )

    return "\n\n".join(lines)


def _lesson_tutor_reply(message: str, context: dict) -> str:
    course = context.get("course")
    lesson = context.get("lesson")

    if lesson:
        return (
            f"I’m Nexa, here to support you inside `{lesson['title']}` from `{course['title']}`.\n\n"
            f"Current focus: {lesson.get('summary', 'This lesson builds one core skill in manageable steps.')} "
            f"A gentle way to look at it is like learning balance on a bicycle: you notice the motion first, try a small movement, and confidence grows from repetition.\n\n"
            f"If it helps, we can take this in one of these ways:\n"
            f"1. A plain-language explanation.\n"
            f"2. A small example with code.\n"
            f"3. A simple analogy or story.\n"
            f"4. A walkthrough of one confusing part.\n\n"
            f"Send the part that feels unclear, and I’ll meet you there without rushing ahead."
        )

    if course:
        return (
            f"I’m Nexa, your learning support companion for `{course['title']}`. "
            f"I can help unpack ideas with examples, analogies, and calmer step-by-step explanations.\n\n"
            f"If something feels tangled, we can start with simpler wording and build back toward the formal version together."
        )

    return (
        "I’m Nexa. I can support the current lesson with examples, stories, simpler rewording, and short walkthroughs. "
        "You can ask something like 'Explain props in a simple way' or 'Can we walk through a small example together?'"
    )


def _platform_support_reply(message: str, context: dict) -> str:
    areas = context.get("areas", [])
    listed = "\n".join(f"- {area['name']}: {area['route']} ({area['description']})" for area in areas[:5])
    return (
        "I can guide users through the platform, even when they are not sure where to click next.\n\n"
        "Key navigation areas right now:\n"
        f"{listed}\n\n"
        "If the user tells me their goal, I should respond with the shortest route to get there. For example: "
        "'to update your profile photo, go to Settings, open Profile settings, then upload the image.'"
    )


def _platform_navigation_reply(message: str, context: dict) -> Optional[str]:
    normalized_message = _normalize_text(message)
    areas = context.get("areas", [])
    if not normalized_message or not areas:
        return None

    best_area = None
    best_score = 0
    message_tokens = _token_set(message)
    for area in areas:
        text = f"{area['name']} {area['description']} {area['route']}"
        area_tokens = _token_set(text)
        score = len(area_tokens & message_tokens)
        if area["name"].lower() in normalized_message:
            score += 3
        if score > best_score:
            best_score = score
            best_area = area

    if best_area and best_score > 0:
        return (
            f"For that task, go to `{best_area['route']}`.\n\n"
            f"What it is for: {best_area['description']}\n\n"
            f"If you want, tell me the exact goal and I will give you the shortest click-by-click path."
        )

    return None


def _should_summarize_course(message: str) -> bool:
    lowered = _normalize_text(message)
    return any(keyword in lowered for keyword in ["summary", "summarize", "aware", "review", "effective", "opinion", "thoughts"])


def _wants_course_improvements(message: str) -> bool:
    lowered = _normalize_text(message)
    improvement_words = ["improve", "improvement", "improve the course", "suggest", "what should we add", "add for start"]
    module_words = ["module", "modules", "lessons", "content", "outline"]
    quantity_words = ["5", "five", "for start"]
    return (
        any(word in lowered for word in improvement_words)
        and any(word in lowered for word in module_words)
        and any(word in lowered for word in quantity_words)
    )


def _wants_course_build_execution(message: str) -> bool:
    lowered = _normalize_text(message)
    execution_phrases = [
        "go ahead",
        "carry on",
        "just carry on",
        "proceed",
        "start drafting",
        "create them",
        "build them",
        "draft them",
        "get ready to create them",
        "go ahead and create",
    ]
    return any(phrase in lowered for phrase in execution_phrases)


def _wants_new_course_creation(message: str) -> bool:
    lowered = _normalize_text(message)
    creation_phrases = [
        "create a new course",
        "create course",
        "build a new course",
        "make a new course",
        "start a new course",
        "create a course called",
        "create a course named",
    ]
    return any(phrase in lowered for phrase in creation_phrases)


def _is_completion_check(message: str) -> bool:
    lowered = _normalize_text(message)
    return any(phrase in lowered for phrase in ["are you done", "is it done", "is it ready", "done yet", "completed"])


def _wants_live_course_apply(message: str) -> bool:
    lowered = _normalize_text(message)
    apply_phrases = [
        "upload to the database",
        "upload them to the database",
        "save to the database",
        "save it to the database",
        "apply to the database",
        "apply it to the course",
        "save to the course",
        "create it in the database",
        "create the course contents and upload",
        "write it to the platform",
        "make it live",
    ]
    return any(phrase in lowered for phrase in apply_phrases)


def _find_recent_artifact_from_history(history: list[dict], artifact_type: str) -> Optional[dict]:
    for item in reversed(history):
        if item.get("role") != "assistant":
            continue
        artifacts = item.get("metadata", {}).get("artifacts", [])
        for artifact in artifacts:
            if artifact.get("artifactType") == artifact_type:
                return artifact
    return None


def _payload_to_curriculum_upsert(payload: dict) -> CourseCurriculumUpsert:
    curriculum_payload = payload.get("curriculum", payload)
    return CourseCurriculumUpsert(
        overview=curriculum_payload.get("overview", ""),
        modules=curriculum_payload.get("modules", []),
        milestoneProjects=curriculum_payload.get("milestoneProjects", curriculum_payload.get("milestone_projects", [])),
    )


async def _find_latest_assignment_artifact(
    assignment: dict,
    artifact_type: str,
    *,
    course_slug: Optional[str] = None,
) -> Optional[dict]:
    query: dict[str, Any] = {
        "assignment_id": assignment["_id"],
        "artifact_type": artifact_type,
    }
    if course_slug:
        query["payload.courseSlug"] = course_slug
    return await agent_artifacts_collection.find_one(query, sort=[("created_at", -1)])


async def _build_course_shell_payload(message: str, current_user: dict) -> Optional[CourseCatalogCreate]:
    title = _extract_course_title(message)
    if not title:
        return None

    category = _infer_course_category(message)
    difficulty = _infer_course_difficulty(message)
    base_slug = _slugify_title(title)
    slug = base_slug
    suffix = 2
    while await course_catalog_collection.find_one({"slug": slug}):
        slug = f"{base_slug}-{suffix}"
        suffix += 1

    instructor_name = _actor_label(current_user)
    description = (
        f"{title} is a {difficulty.lower()} {category.lower()} course on Deveda. "
        "It is structured with guided lessons, checkpoint quizzes, and milestone practice so learners can build confidence step by step."
    )

    return CourseCatalogCreate(
        slug=slug,
        title=title,
        description=description,
        category=category,
        difficulty=difficulty,
        duration=0,
        totalQuizzes=0,
        totalLessons=0,
        instructor=instructor_name,
        prerequisites=[],
        tags=_default_course_tags(category, title),
        thumbnail="",
        thumbnailPublicId="",
    )


async def _build_course_catalog_draft_payload(
    message: str,
    current_user: dict,
    draft_payload: Optional[dict] = None,
) -> dict:
    draft_payload = draft_payload if isinstance(draft_payload, dict) else {}
    generated = _openai_json_request(
        [
            {
                "role": "system",
                "content": (
                    "You are Deveda's course catalog drafting engine. Return valid JSON only. "
                    "Create a concise course metadata draft for a coding course authoring form."
                ),
            },
            {
                "role": "user",
                "content": (
                    "Return JSON with this exact shape: "
                    "{\"title\": string, \"description\": string, \"category\": string, \"difficulty\": string, "
                    "\"duration\": number, \"totalLessons\": number, \"totalQuizzes\": number, "
                    "\"prerequisites\": string[], \"tags\": string[]}. "
                    f"Current draft: {json.dumps(draft_payload, default=str)}. "
                    f"Instructor request: {message}"
                ),
            },
        ],
        timeout=18,
    ) or {}

    title = str(generated.get("title") or draft_payload.get("title") or _extract_course_title(message) or "New Course").strip()
    category = str(generated.get("category") or draft_payload.get("category") or _infer_course_category(message)).strip() or "Frontend Development"
    difficulty = str(generated.get("difficulty") or draft_payload.get("difficulty") or _infer_course_difficulty(message)).strip() or "Beginner"
    description = str(
        generated.get("description")
        or draft_payload.get("description")
        or (
            f"{title} is a {difficulty.lower()} {category.lower()} course on Deveda. "
            "It is structured with guided lessons, checkpoint quizzes, and milestone practice so learners can build confidence step by step."
        )
    ).strip()

    base_slug = _slugify_title(str(draft_payload.get("slug") or generated.get("slug") or title))
    slug = base_slug
    suffix = 2
    while await course_catalog_collection.find_one({"slug": slug}):
        slug = f"{base_slug}-{suffix}"
        suffix += 1

    return {
        "slug": slug,
        "title": title,
        "description": description,
        "category": category,
        "difficulty": difficulty,
        "duration": int(generated.get("duration") or draft_payload.get("duration") or 240),
        "totalLessons": int(generated.get("totalLessons") or draft_payload.get("totalLessons") or 12),
        "totalQuizzes": int(generated.get("totalQuizzes") or draft_payload.get("totalQuizzes") or 4),
        "instructor": str(draft_payload.get("instructor") or _actor_label(current_user)),
        "prerequisites": _coerce_string_list(generated.get("prerequisites"), draft_payload.get("prerequisites") or []),
        "tags": _coerce_string_list(generated.get("tags"), draft_payload.get("tags") or _default_course_tags(category, title)),
        "thumbnail": str(draft_payload.get("thumbnail") or ""),
        "thumbnailPublicId": str(draft_payload.get("thumbnailPublicId") or ""),
    }


async def _create_course_catalog_draft_artifact(
    assignment: dict,
    instruction: str,
    current_user: dict,
    *,
    thread_id: Optional[ObjectId] = None,
    draft_payload: Optional[dict] = None,
) -> dict:
    payload = await _build_course_catalog_draft_payload(instruction, current_user, draft_payload=draft_payload)
    summary = f"Prepared a course draft for {payload['title']} so the instructor can review and submit it."
    return await _store_artifact(
        assignment,
        "course_catalog_draft",
        f"{payload['title']} course draft",
        summary,
        payload,
        thread_id=thread_id,
        route="/instructor/dashboard/courses",
    )


async def _create_course_shell_on_platform(
    assignment: dict,
    message: str,
    current_user: dict,
    *,
    thread_id: Optional[ObjectId] = None,
) -> Optional[dict]:
    payload = await _build_course_shell_payload(message, current_user)
    if payload is None:
        return None

    created = await CourseCatalogService.create_course_catalog(payload)
    scaffold = await ContentService.get_course_curriculum(payload.slug)
    artifact_payload = {
        "courseSlug": payload.slug,
        "course": created["data"],
        "curriculum": scaffold["data"],
        "createdBy": _actor_label(current_user),
    }
    summary = f"Created a new course shell for {payload.title} and opened the scaffolded curriculum workspace."
    return await _store_artifact(
        assignment,
        "course_shell",
        f"{payload.title} course shell",
        summary,
        artifact_payload,
        thread_id=thread_id,
        route=f"/instructor/dashboard/cms?course={payload.slug}",
    )


async def _resolve_curriculum_source_artifact(
    assignment: dict,
    payload: AgentActionCreate,
    context: dict,
) -> Optional[dict]:
    course_slug = payload.courseSlug or context.get("matchedCourseSlug")
    allowed_artifact_types = {"curriculum_draft", "course_content_generation"}
    if payload.artifactId:
        artifact = await _get_artifact_or_404(payload.artifactId)
        if str(artifact.get("assignment_id")) != str(assignment["_id"]):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={"message": "This artifact does not belong to the selected agent assignment"},
            )
        if artifact.get("artifact_type") not in allowed_artifact_types:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"message": "Only generated curriculum artifacts can be applied to a live course"},
            )
        return artifact

    generated_artifact = await _find_latest_assignment_artifact(assignment, "course_content_generation", course_slug=course_slug)
    if generated_artifact:
        return generated_artifact
    return await _find_latest_assignment_artifact(assignment, "curriculum_draft", course_slug=course_slug)


async def _build_controlled_course_builder_reply(
    assignment: dict,
    message: str,
    context: dict,
    history: list[dict],
    thread_id: ObjectId,
    current_user: dict,
) -> Optional[dict]:
    if _wants_new_course_creation(message):
        created_course = await _create_course_shell_on_platform(assignment, message, current_user, thread_id=thread_id)
        if created_course:
            artifact = _serialize_artifact(created_course)
            created_title = created_course.get("payload", {}).get("course", {}).get("title", created_course["title"])
            return {
                "content": (
                    f"I created a new course shell for `{created_title}` and scaffolded its curriculum workspace.\n\n"
                    "You can now open the curriculum studio to refine modules, lessons, milestone projects, and quiz checkpoints."
                ),
                "metadata": {
                    "provider": "deveda-controlled",
                    "artifacts": [artifact],
                    "route": artifact.get("route"),
                    "routeLabel": "Open curriculum studio",
                },
            }
        return {
            "content": (
                "I can create the course directly on the platform, but I need a clearer title first. "
                "Try a message like `Create a new course called \"Frontend Developer Intermediate\"`."
            ),
            "metadata": {"provider": "deveda-controlled"},
        }

    if context.get("course") and _should_summarize_course(message):
        return {
            "content": _course_summary_reply(context),
            "metadata": {"provider": "deveda-controlled"},
        }

    if context.get("course") and _wants_course_improvements(message):
        return {
            "content": _build_course_improvement_reply(context),
            "metadata": {"provider": "deveda-controlled"},
        }

    if context.get("course") and _wants_live_course_apply(message):
        suggested_modules = _build_extension_modules(context["course"], context.get("curriculum"))
        latest_draft = await _find_latest_assignment_artifact(
            assignment,
            "curriculum_draft",
            course_slug=context.get("matchedCourseSlug"),
        )
        created_draft = None
        if latest_draft is None:
            created_draft = await _create_curriculum_draft_artifact(
                assignment,
                context,
                message,
                thread_id=thread_id,
                suggested_modules=suggested_modules,
            )
            latest_draft = created_draft

        applied_modules = latest_draft.get("payload", {}).get("modules", [])[-5:] if latest_draft else suggested_modules
        applied_artifact = await _apply_curriculum_to_platform(
            assignment,
            context,
            message,
            _actor_label(current_user),
            thread_id=thread_id,
            source_artifact=latest_draft,
            suggested_modules=suggested_modules,
        )
        artifacts = []
        if created_draft:
            artifacts.append(_serialize_artifact(created_draft))
        if applied_artifact:
            artifacts.append(_serialize_artifact(applied_artifact))
        module_lines = "\n".join(_module_to_markdown(module, index) for index, module in enumerate(applied_modules, start=1))
        return {
            "content": (
                f"I applied the course update to the platform for `{context['course']['title']}`.\n\n"
                f"Created or confirmed these expansion modules:\n{module_lines}\n\n"
                "The live curriculum is now saved through the platform curriculum service, and the course lesson, quiz, and duration totals were synced."
            ),
            "metadata": {
                "provider": "deveda-controlled",
                "artifacts": artifacts,
                "route": "/instructor/dashboard/cms",
                "routeLabel": "Open curriculum studio",
            },
        }

    if context.get("course") and _wants_course_build_execution(message):
        suggested_modules = _build_extension_modules(context["course"], context.get("curriculum"))
        draft_artifact = await _create_curriculum_draft_artifact(
            assignment,
            context,
            message,
            thread_id=thread_id,
            suggested_modules=suggested_modules,
        )
        artifacts = [_serialize_artifact(draft_artifact)] if draft_artifact else []
        module_lines = "\n".join(_module_to_markdown(module, index) for index, module in enumerate(suggested_modules, start=1))
        return {
            "content": (
                f"I carried it forward and created the first structured draft for `{context['course']['title']}`.\n\n"
                f"Added modules:\n{module_lines}\n\n"
                "This first pass is shaped for beginners: each module has a clear reason to exist, starter lessons, and a checkpoint. "
                "You can now review the saved draft and refine the lesson depth later."
            ),
            "metadata": {"provider": "deveda-controlled", "artifacts": artifacts},
        }

    if _is_completion_check(message):
        applied_artifact = _find_recent_artifact_from_history(history, "curriculum_apply_result")
        if applied_artifact:
            return {
                "content": (
                    f"Yes. The live curriculum update is complete as `{applied_artifact['title']}`.\n\n"
                    "The course was saved to the platform and the latest curriculum is ready in the curriculum studio."
                ),
                "metadata": {
                    "provider": "deveda-controlled",
                    "artifacts": [applied_artifact],
                    "route": "/instructor/dashboard/cms",
                    "routeLabel": "Open curriculum studio",
                },
            }

        artifact = _find_recent_artifact_from_history(history, "curriculum_draft")
        if artifact:
            return {
                "content": (
                    f"Yes. The first draft is ready as `{artifact['title']}`.\n\n"
                    f"It includes the 5 suggested expansion modules and is ready for review in the related workspace."
                ),
                "metadata": {"provider": "deveda-controlled", "artifacts": [artifact]},
            }

    return None


def _deterministic_reply(agent_type: str, message: str, context: dict) -> Optional[str]:
    if agent_type == "course_builder" and context.get("course") and _should_summarize_course(message):
        return _course_summary_reply(context)

    if agent_type == "platform_support":
        navigation = _platform_navigation_reply(message, context)
        if navigation:
            return navigation

    if agent_type == "lesson_tutor" and context.get("course") and _should_summarize_course(message):
        return _course_summary_reply(context)

    return None


def _supports_curriculum_draft_request(message: str) -> bool:
    lowered = _normalize_text(message)
    return "draft" in lowered and any(keyword in lowered for keyword in ["curriculum", "outline", "course plan", "module plan"])


def _supports_planning_note_request(message: str) -> bool:
    lowered = _normalize_text(message)
    return any(keyword in lowered for keyword in ["save planning note", "save lesson plan", "save note", "planning note", "lesson note"])


def _fallback_reply(agent_type: str, message: str, context: dict) -> str:
    direct_reply = _deterministic_reply(agent_type, message, context)
    if direct_reply:
        return direct_reply

    if agent_type == "course_builder":
        return _course_builder_reply(message, context)
    if agent_type == "progress_analyst":
        return _progress_analyst_reply(message, context)
    if agent_type == "lesson_tutor":
        return _lesson_tutor_reply(message, context)
    return _platform_support_reply(message, context)


def _system_prompt(agent_type: str, context: dict) -> str:
    if agent_type == "course_builder":
        return "You are Deveda's Course Builder agent. Always use the provided platform context first. If a course is present in context, never say you lack access to course details."
    if agent_type == "progress_analyst":
        return "You are Deveda's Progress Analyst agent. Review learner progress and turn it into actionable lesson planning guidance for instructors."
    if agent_type == "lesson_tutor":
        return (
            "You are Nexa, Deveda's learner support companion. "
            "Be warm, calm, and encouraging. Support rather than command. "
            "Avoid bossy or overly directive phrasing. Prefer collaborative language like 'we can', 'it may help to', and 'if you want'. "
            "Explain clearly, kindly, and concretely, using the provided lesson and course context before answering."
        )
    return "You are Deveda's Platform Support agent. Help users navigate the product and understand where to go next. Use the current platform map from context instead of generic guesses."


def _build_openai_messages(agent_type: str, context: dict, history: list[dict], user_message: str) -> list[dict]:
    messages = [{"role": "system", "content": _system_prompt(agent_type, context)}]
    context_payload = json.dumps(context, default=str)
    messages.append({"role": "system", "content": f"Current context: {context_payload}"})
    for item in history[-6:]:
        messages.append({"role": item["role"], "content": item["content"]})
    messages.append({"role": "user", "content": user_message})
    return messages


def _call_openai(agent_type: str, context: dict, history: list[dict], user_message: str) -> Optional[dict]:
    messages = _build_openai_messages(agent_type, context, history, user_message)
    try:
        content = AgentGraphRuntime.invoke_text_response_sync(messages, timeout=25, temperature=0.7)
        if content:
            return {"content": content, "metadata": {"provider": "openai", "model": OPENAI_MODEL, "orchestrator": "langgraph"}}
    except Exception:
        pass

    if not OPENAI_API_KEY:
        return None

    payload = {
        "model": OPENAI_MODEL,
        "messages": messages,
        "temperature": 0.7,
    }
    req = request.Request(
        "https://api.openai.com/v1/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {OPENAI_API_KEY}",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    try:
        with request.urlopen(req, timeout=25) as response:
            body = json.loads(response.read().decode("utf-8"))
            content = body["choices"][0]["message"]["content"].strip()
            return {"content": content, "metadata": {"provider": "openai", "model": OPENAI_MODEL}}
    except (error.HTTPError, error.URLError, KeyError, IndexError, json.JSONDecodeError):
        return None


async def _build_context_bundle(assignment: dict, message_payload: AgentMessageCreate) -> tuple[dict, list[str]]:
    tools_used: list[str] = []
    course_slug = message_payload.courseSlug or assignment.get("course_slug")
    lesson_slug = message_payload.lessonSlug or assignment.get("lesson_slug")
    target_user_id = assignment.get("target_user_id")

    context: dict[str, Any] = {}

    if assignment["agent_type"] in {"lesson_tutor", "course_builder"}:
        context.update(await _collect_course_context(course_slug, lesson_slug, message_payload.message))
        tools_used.append("scan_course_content")

    if assignment["agent_type"] == "progress_analyst":
        context.update(await _collect_progress_context(target_user_id))
        tools_used.append("scan_student_progress")

    if assignment["agent_type"] == "platform_support":
        requester = await _get_user_or_404(assignment["user_id"])
        context.update(await _collect_platform_context(requester))
        tools_used.append("scan_platform_map")

    if message_payload.lessonTitle:
        context["lessonTitle"] = message_payload.lessonTitle
    if message_payload.currentProgress is not None:
        context["currentProgress"] = message_payload.currentProgress

    return context, tools_used


async def _create_curriculum_draft_artifact(
    assignment: dict,
    context: dict,
    instruction: str,
    *,
    thread_id: Optional[ObjectId] = None,
    suggested_modules: Optional[list[dict]] = None,
) -> Optional[dict]:
    course = context.get("course")
    if not course:
        return None

    payload = _build_curriculum_draft_payload(course, context.get("curriculum"), instruction, suggested_modules=suggested_modules)
    summary = f"Drafted a fuller curriculum outline for {course['title']} with modules, assessments, and milestone work."
    return await _store_artifact(
        assignment,
        "curriculum_draft",
        f"{course['title']} curriculum draft",
        summary,
        payload,
        thread_id=thread_id,
        route=f"/instructor/dashboard/cms",
    )


async def _apply_curriculum_to_platform(
    assignment: dict,
    context: dict,
    instruction: str,
    applied_by: str,
    *,
    thread_id: Optional[ObjectId] = None,
    source_artifact: Optional[dict] = None,
    suggested_modules: Optional[list[dict]] = None,
) -> Optional[dict]:
    course = context.get("course")
    if not course:
        return None

    source_payload = (
        source_artifact.get("payload", {})
        if source_artifact
        else _build_curriculum_draft_payload(
            course,
            context.get("curriculum"),
            instruction,
            suggested_modules=suggested_modules,
        )
    )
    curriculum_payload = _payload_to_curriculum_upsert(source_payload)
    saved = await ContentService.upsert_course_curriculum(course["slug"], curriculum_payload, applied_by)
    saved_curriculum = saved["data"]

    if source_artifact:
        await agent_artifacts_collection.update_one(
            {"_id": source_artifact["_id"]},
            {"$set": {"status": "applied", "applied_at": datetime.utcnow(), "applied_by": applied_by}},
        )

    applied_payload = {
        "courseSlug": course["slug"],
        "instruction": instruction,
        "sourceArtifactId": str(source_artifact["_id"]) if source_artifact else None,
        "curriculum": saved_curriculum,
        "appliedBy": applied_by,
        "appliedAt": datetime.utcnow(),
    }
    summary = f"Applied curriculum changes to {course['title']} and synced lesson, quiz, and duration totals."
    return await _store_artifact(
        assignment,
        "curriculum_apply_result",
        f"{course['title']} live curriculum update",
        summary,
        applied_payload,
        thread_id=thread_id,
        route="/instructor/dashboard/cms",
    )


async def _create_planning_note_artifact(
    assignment: dict,
    context: dict,
    instruction: str,
    *,
    thread_id: Optional[ObjectId] = None,
) -> Optional[dict]:
    learner = context.get("learner")
    summary = context.get("summary", {})
    if not learner:
        return None

    payload = {
        "learner": learner,
        "instruction": instruction,
        "lessonPlanNote": (
            f"Plan the next lesson for {learner['firstName']} {learner['lastName']} around one concrete win. "
            f"Average progress is {summary.get('averageProgress', 0)}% and quiz pass rate is {summary.get('passRate', 0)}%. "
            "Start with a worked example, then shift to one guided modification task before independent practice."
        ),
        "summary": summary,
        "courses": context.get("courses", [])[:4],
    }
    note_summary = f"Saved a lesson-planning note for {learner['firstName']} {learner['lastName']} based on recent progress."
    return await _store_artifact(
        assignment,
        "lesson_plan_note",
        f"{learner['firstName']} {learner['lastName']} lesson plan note",
        note_summary,
        payload,
        thread_id=thread_id,
        route="/instructor/dashboard/analytics",
    )


async def _create_lesson_content_plan_artifact(
    assignment: dict,
    context: dict,
    instruction: str,
    *,
    thread_id: Optional[ObjectId] = None,
) -> Optional[dict]:
    course = context.get("course")
    lesson = context.get("lesson") or _resolve_working_lesson_context(context)
    if not course or not lesson:
        return None

    payload = _build_lesson_content_plan_payload(course, lesson, instruction)
    summary = f"Planned the teaching arc, practice flow, and best-practice structure for {lesson['title']}."
    return await _store_artifact(
        assignment,
        "lesson_content_plan",
        f"{lesson['title']} lesson plan",
        summary,
        payload,
        thread_id=thread_id,
        route=f"/instructor/dashboard/cms?course={course['slug']}",
    )


async def _create_generated_lesson_content_artifact(
    assignment: dict,
    context: dict,
    instruction: str,
    *,
    thread_id: Optional[ObjectId] = None,
) -> Optional[dict]:
    course = context.get("course")
    lesson = context.get("lesson") or _resolve_working_lesson_context(context)
    if not course or not lesson:
        return None

    plan_payload = _build_lesson_content_plan_payload(course, lesson, instruction)
    suggestion = _build_generated_lesson_payload(course, lesson, plan_payload)
    payload = {
        "courseSlug": course["slug"],
        "lessonSlug": lesson["slug"],
        "moduleTitle": lesson.get("moduleTitle", "Module"),
        "lesson": suggestion,
        "plan": plan_payload,
        "instruction": instruction,
    }
    summary = f"Generated a full lesson package for {lesson['title']} with objectives, markdown, practice, and workspace guidance."
    return await _store_artifact(
        assignment,
        "lesson_content_generation",
        f"{lesson['title']} generated lesson",
        summary,
        payload,
        thread_id=thread_id,
        route=f"/instructor/dashboard/cms?course={course['slug']}",
    )


async def _create_course_content_plan_artifact(
    assignment: dict,
    context: dict,
    instruction: str,
    *,
    thread_id: Optional[ObjectId] = None,
) -> Optional[dict]:
    course = context.get("course")
    if not course:
        return None

    working_curriculum = _resolve_working_curriculum(
        context,
        context.get("draftPayload") if isinstance(context.get("draftPayload"), dict) else None,
    )
    payload = _build_course_content_plan_payload(course, working_curriculum, instruction)
    summary = f"Planned the background curriculum and lesson generation workflow for {course['title']}."
    return await _store_artifact(
        assignment,
        "course_content_plan",
        f"{course['title']} course generation plan",
        summary,
        payload,
        thread_id=thread_id,
        route=f"/instructor/dashboard/cms?course={course['slug']}",
    )


async def _create_generated_course_content_artifact(
    assignment: dict,
    context: dict,
    instruction: str,
    *,
    thread_id: Optional[ObjectId] = None,
) -> Optional[dict]:
    course = context.get("course")
    if not course:
        return None

    working_curriculum = _resolve_working_curriculum(
        context,
        context.get("draftPayload") if isinstance(context.get("draftPayload"), dict) else None,
    )
    plan_payload = _build_course_content_plan_payload(course, working_curriculum, instruction)
    payload = _build_generated_course_payload(course, working_curriculum, instruction, plan_payload=plan_payload)
    summary = f"Generated a course outline for {course['title']} that is ready for module-by-module expansion."
    return await _store_artifact(
        assignment,
        "course_content_generation",
        f"{course['title']} generated course outline",
        summary,
        payload,
        thread_id=thread_id,
        route=f"/instructor/dashboard/cms?course={course['slug']}",
    )


def _resolve_working_curriculum(context: dict, draft_payload: Optional[dict]) -> dict:
    if isinstance(draft_payload, dict) and isinstance(draft_payload.get("modules"), list):
        return {
            "courseSlug": draft_payload.get("courseSlug", context.get("matchedCourseSlug")),
            "overview": draft_payload.get("overview", ""),
            "modules": draft_payload.get("modules", []),
            "milestoneProjects": draft_payload.get("milestoneProjects", []),
        }

    curriculum = context.get("curriculum")
    if curriculum:
        return {
            "courseSlug": context.get("matchedCourseSlug"),
            "overview": curriculum.get("overview", ""),
            "modules": curriculum.get("modules", []),
            "milestoneProjects": curriculum.get("milestone_projects", curriculum.get("milestoneProjects", [])),
        }

    course = context.get("course")
    if course:
        scaffold = build_curriculum_scaffold(course)
        return {
            "courseSlug": course.get("slug"),
            "overview": scaffold.get("overview", ""),
            "modules": scaffold.get("modules", []),
            "milestoneProjects": scaffold.get("milestone_projects", []),
        }
    return {"courseSlug": "", "overview": "", "modules": [], "milestoneProjects": []}


def _resolve_working_lesson_context(context: dict) -> Optional[dict]:
    draft_payload = context.get("draftPayload") if isinstance(context.get("draftPayload"), dict) else None
    if isinstance(draft_payload, dict):
        draft_lesson = draft_payload.get("lesson")
        if isinstance(draft_lesson, dict):
            raw_module_order = draft_lesson.get("moduleOrder", draft_payload.get("moduleOrder", 1))
            try:
                module_order = max(int(raw_module_order or 1), 1)
            except (TypeError, ValueError):
                module_order = 1
            return {
                **draft_lesson,
                "moduleTitle": str(draft_lesson.get("moduleTitle", draft_payload.get("moduleTitle", "Module"))).strip() or "Module",
                "moduleOrder": module_order,
            }

    working_curriculum = _resolve_working_curriculum(context, draft_payload)
    requested_lesson_slug = str(context.get("requestedLessonSlug", "") or "").strip()
    if not requested_lesson_slug:
        return None

    for module_index, module in enumerate(working_curriculum.get("modules", []), start=1):
        lessons = module.get("lessons", []) if isinstance(module.get("lessons"), list) else []
        for lesson in lessons:
            if str(lesson.get("slug", "")).strip() == requested_lesson_slug:
                raw_module_order = module.get("order", module_index)
                try:
                    module_order = max(int(raw_module_order or module_index), 1)
                except (TypeError, ValueError):
                    module_order = module_index
                return {
                    **lesson,
                    "moduleTitle": str(module.get("title", "Module")).strip() or "Module",
                    "moduleOrder": module_order,
                }

    return None


def _build_fallback_module_payload(course: dict, module: dict, module_order: int, instruction: str) -> dict:
    seed_module = module if module and not _is_generic_title(str(module.get("title", ""))) and not _is_scaffold_origin(module) else _module_generation_seed(
        course,
        {"modules": [module] if module else []},
        module_order,
    )
    module_title = seed_module.get("title", f"Module {module_order}")
    lessons = seed_module.get("lessons", []) if isinstance(seed_module.get("lessons"), list) and seed_module.get("lessons") else [
        {
            "title": f"{module_title} foundations",
            "slug": _slugify_title(f"{course['slug']}-{module_title}-foundations"),
            "summary": f"Introduce the main idea in {module_title}.",
            "durationMinutes": 20,
            "contentType": "lesson",
        }
    ]
    generated_lessons = []
    for lesson_index, lesson in enumerate(lessons, start=1):
        lesson_context = {
            **lesson,
            "title": lesson.get("title", f"{module_title} lesson {lesson_index}"),
            "slug": lesson.get("slug", _slugify_title(f"{course['slug']}-{module_title}-lesson-{lesson_index}")),
            "summary": lesson.get("summary", f"Use {module_title} in a practical way."),
            "durationMinutes": lesson.get("durationMinutes", 20),
            "contentType": lesson.get("contentType", "lesson"),
            "moduleTitle": module_title,
        }
        lesson_plan = _build_lesson_content_plan_payload(course, lesson_context, f"{instruction} Build complete lesson content for {lesson_context['title']}.")
        generated_lessons.append(_build_generated_lesson_payload(course, lesson_context, lesson_plan))

    return {
        "title": module_title,
        "description": seed_module.get("description") or f"Guide learners through {module_title.lower()} with real examples, guided repetition, and a checkpoint.",
        "order": seed_module.get("order", module_order),
        "lessons": generated_lessons,
        "assessmentTitle": seed_module.get("assessmentTitle") or f"{module_title} applied checkpoint",
        "assessmentQuizId": seed_module.get("assessmentQuizId") or f"{course['slug']}-module-{module_order}-applied-check",
    }


def _generate_module_payload_with_openai(course: dict, curriculum: dict, module: dict, module_order: int, instruction: str) -> Optional[dict]:
    module_seed = _merge_module_with_seed(course, curriculum, module, module_order)
    context_payload = {
        "course": {
            "title": course.get("title"),
            "slug": course.get("slug"),
            "description": course.get("description"),
            "category": course.get("category"),
            "difficulty": course.get("difficulty"),
            "tags": course.get("tags", []),
            "prerequisites": course.get("prerequisites", []),
        },
        "moduleSeed": module_seed,
        "moduleThemeHint": _fallback_theme_for_module(course, module_order),
        "moduleOrder": module_order,
        "approvedContextModules": _authoritative_modules(curriculum, exclude_order=module_order),
        "instruction": instruction,
    }
    return _openai_json_request(
        [
            {
                "role": "system",
                "content": (
                    "You are Deveda's curriculum generation engine. Return valid JSON only. "
                    "Expand one module into complete, real lesson content. Do not return suggestions or placeholders. "
                    "Do not reuse generic scaffold titles like Foundation Sprint, orientation, or first guided implementation. "
                    "Teach the actual topic directly inside the lesson body."
                ),
            },
            {
                "role": "user",
                "content": (
                    "Create JSON with this exact shape: "
                    "{\"title\": string, \"description\": string, \"order\": number, \"assessmentTitle\": string, "
                    "\"lessons\": [{\"title\": string, \"slug\": string, \"summary\": string, "
                    "\"durationMinutes\": number, \"contentType\": string, \"learningObjectives\": string[], \"keyTakeaways\": string[], "
                    "\"contentMarkdown\": string, \"practicePrompt\": string, \"instructorNotes\": string}]}. "
                    "Use the module seed as a topic and sequencing hint, not as fixed wording. Rewrite generic titles into concrete topic names. "
                    "Define the concept, explain the example, and describe the practice directly instead of saying the lesson will do those things. "
                    f"Context: {json.dumps(context_payload, default=str)}"
                ),
            },
        ],
        timeout=24,
    )


async def _create_generated_module_content_artifact(
    assignment: dict,
    context: dict,
    payload: AgentActionCreate,
    instruction: str,
    *,
    thread_id: Optional[ObjectId] = None,
) -> Optional[dict]:
    course = context.get("course")
    if not course or not payload.moduleOrder:
        return None

    working_curriculum = _resolve_working_curriculum(context, payload.draftPayload)
    module_index = payload.moduleOrder - 1
    modules = working_curriculum.get("modules", [])
    base_module = modules[module_index] if module_index < len(modules) else {"title": f"Module {payload.moduleOrder}", "lessons": []}
    generated_module = _generate_module_payload_with_openai(course, working_curriculum, base_module, payload.moduleOrder, instruction)
    if generated_module:
        generated_module = _merge_module_with_seed(course, working_curriculum, generated_module, payload.moduleOrder)
    if not generated_module or _is_generic_title(str(generated_module.get("title", ""))):
        generated_module = _build_fallback_module_payload(
            course,
            base_module,
            payload.moduleOrder,
            instruction,
        )
    normalized_module = _normalize_generated_module_payload(course, generated_module, payload.moduleOrder)
    artifact_payload = {
        "courseSlug": course["slug"],
        "moduleOrder": payload.moduleOrder,
        "module": normalized_module,
        "instruction": instruction,
    }
    summary = f"Generated full module content for module {payload.moduleOrder} in {course['title']}."
    return await _store_artifact(
        assignment,
        "module_content_generation",
        f"{course['title']} module {payload.moduleOrder} generated content",
        summary,
        artifact_payload,
        thread_id=thread_id,
        route=f"/instructor/dashboard/cms?course={course['slug']}",
    )


async def _create_generated_question_content_artifact(
    assignment: dict,
    context: dict,
    payload: AgentActionCreate,
    instruction: str,
    *,
    thread_id: Optional[ObjectId] = None,
) -> Optional[dict]:
    draft_payload = payload.draftPayload if isinstance(payload.draftPayload, dict) else {}
    quiz_id = str(draft_payload.get("quizId", "")).strip()
    if not quiz_id:
        return None

    course = context.get("course")
    question_payload = _openai_json_request(
        [
            {
                "role": "system",
                "content": (
                    "You are Deveda's assessment authoring engine. Return valid JSON only. "
                    "Write one complete quiz question with real instructional wording, plausible distractors, and a clear explanation."
                ),
            },
            {
                "role": "user",
                "content": (
                    "Create JSON with this exact shape: "
                    "{\"quizId\": string, \"question\": string, \"options\": string[], \"correctAnswer\": string, "
                    "\"explanation\": string, \"points\": number, \"timeLimit\": number, \"questionType\": string, "
                    "\"difficulty\": string, \"isActive\": boolean}. "
                    f"Current draft: {json.dumps(draft_payload, default=str)}. "
                    f"Course context: {json.dumps(course or {}, default=str)}. "
                    f"Instructor request: {instruction}"
                ),
            },
        ],
        timeout=18,
    ) or {}

    resolved_payload = {
        "quizId": quiz_id,
        "question": str(question_payload.get("question") or instruction or "What is the main idea behind this topic?").strip(),
        "options": _coerce_string_list(question_payload.get("options"), ["Option A", "Option B", "Option C", "Option D"])[:4],
        "correctAnswer": str(question_payload.get("correctAnswer") or "").strip(),
        "explanation": str(question_payload.get("explanation") or "Explain why the correct option is right and why the distractors are wrong.").strip(),
        "points": int(question_payload.get("points") or draft_payload.get("points") or 1),
        "timeLimit": int(question_payload.get("timeLimit") or draft_payload.get("timeLimit") or 60),
        "questionType": str(question_payload.get("questionType") or draft_payload.get("questionType") or "multiple_choice"),
        "difficulty": str(question_payload.get("difficulty") or draft_payload.get("difficulty") or "Medium"),
        "isActive": bool(question_payload.get("isActive", draft_payload.get("isActive", True))),
    }
    if resolved_payload["correctAnswer"] not in resolved_payload["options"]:
        resolved_payload["correctAnswer"] = resolved_payload["options"][0]

    summary = f"Generated a question draft for quiz {quiz_id} that can be reviewed and submitted directly."
    return await _store_artifact(
        assignment,
        "question_content_generation",
        f"{quiz_id} question draft",
        summary,
        resolved_payload,
        thread_id=thread_id,
        route="/instructor/dashboard/questions",
    )


async def _create_lesson_content_suggestion_artifact(
    assignment: dict,
    context: dict,
    instruction: str,
    *,
    thread_id: Optional[ObjectId] = None,
) -> Optional[dict]:
    course = context.get("course")
    lesson = context.get("lesson") or _resolve_working_lesson_context(context)
    if not course or not lesson:
        return None

    plan_payload = _build_lesson_content_plan_payload(course, lesson, instruction)
    suggestion = _build_generated_lesson_payload(course, lesson, plan_payload)
    payload = {
        "courseSlug": course["slug"],
        "lessonSlug": lesson["slug"],
        "moduleTitle": lesson.get("moduleTitle", "Module"),
        "lesson": suggestion,
        "guidance": plan_payload.get("bestPractices", []),
        "plan": plan_payload,
        "instruction": instruction,
    }
    summary = f"Prepared a richer lesson suggestion for {lesson['title']} in {course['title']}."
    return await _store_artifact(
        assignment,
        "lesson_content_suggestion",
        f"{lesson['title']} lesson suggestion",
        summary,
        payload,
        thread_id=thread_id,
        route=f"/instructor/dashboard/cms?course={course['slug']}",
    )


async def _execute_agent_action_from_context(
    assignment: dict,
    payload: AgentActionCreate,
    context: dict,
    current_user: dict,
) -> Optional[dict]:
    artifact = None
    if payload.actionType == "draft_course_catalog":
        artifact = await _create_course_catalog_draft_artifact(
            assignment,
            payload.instruction or "",
            current_user,
            draft_payload=payload.draftPayload if isinstance(payload.draftPayload, dict) else None,
        )
    elif payload.actionType == "create_course_shell":
        artifact = await _create_course_shell_on_platform(
            assignment,
            payload.instruction or "",
            current_user,
        )
    elif payload.actionType == "create_curriculum_draft":
        artifact = await _create_curriculum_draft_artifact(assignment, context, payload.instruction or "")
    elif payload.actionType == "apply_curriculum_to_course":
        source_artifact = await _resolve_curriculum_source_artifact(assignment, payload, context)
        if not source_artifact and assignment["agent_type"] == "course_builder":
            suggested_modules = _build_extension_modules(context["course"], context.get("curriculum")) if context.get("course") else None
            source_artifact = await _create_curriculum_draft_artifact(
                assignment,
                context,
                payload.instruction or payload.actionType,
                suggested_modules=suggested_modules,
            )
        artifact = await _apply_curriculum_to_platform(
            assignment,
            context,
            payload.instruction or "",
            _actor_label(current_user),
            source_artifact=source_artifact,
        )
    elif payload.actionType == "suggest_lesson_content":
        artifact = await _create_lesson_content_suggestion_artifact(
            assignment,
            context,
            payload.instruction or "",
        )
    elif payload.actionType == "plan_lesson_content":
        artifact = await _create_lesson_content_plan_artifact(
            assignment,
            context,
            payload.instruction or "",
        )
    elif payload.actionType == "generate_lesson_content":
        artifact = await _create_generated_lesson_content_artifact(
            assignment,
            context,
            payload.instruction or "",
        )
    elif payload.actionType == "plan_course_content":
        artifact = await _create_course_content_plan_artifact(
            assignment,
            context,
            payload.instruction or "",
        )
    elif payload.actionType == "generate_course_content":
        artifact = await _create_generated_course_content_artifact(
            assignment,
            context,
            payload.instruction or "",
        )
    elif payload.actionType == "generate_module_content":
        artifact = await _create_generated_module_content_artifact(
            assignment,
            context,
            payload,
            payload.instruction or "",
        )
    elif payload.actionType == "generate_question_content":
        artifact = await _create_generated_question_content_artifact(
            assignment,
            context,
            payload,
            payload.instruction or "",
        )
    elif payload.actionType == "save_planning_note":
        if payload.targetUserId:
            context.update(await _collect_progress_context(validate_object_id(payload.targetUserId)))
        artifact = await _create_planning_note_artifact(assignment, context, payload.instruction or "")

    return artifact


class AgentService:
    @staticmethod
    async def get_catalog(current_user: dict):
        catalog = []
        for template in AGENT_TEMPLATES.values():
            if current_user.get("role") not in template["allowedRequesterRoles"] and current_user.get("role") != "Admin":
                continue
            catalog.append(template)
        return {"message": "Agent catalog fetched", "data": catalog}

    @staticmethod
    async def create_request(payload: AgentRequestCreate, current_user: dict):
        template = AGENT_TEMPLATES.get(payload.agentType)
        if not template:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"message": "Unknown agent type"},
            )

        if current_user.get("role") not in template["allowedRequesterRoles"] and current_user.get("role") != "Admin":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={"message": "You cannot request this agent type"},
            )

        target_user_id = validate_object_id(payload.targetUserId) if payload.targetUserId else None
        if target_user_id:
            target_user = await _get_user_or_404(target_user_id)
            if target_user.get("role") != "Student":
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail={"message": "Target user must be a student"},
                )

        now = datetime.utcnow()
        request_needs_approval = _request_requires_approval(template, current_user)
        existing = await agent_assignments_collection.find_one(
            _assignment_identity_query(
                user_id=current_user["_id"],
                agent_type=payload.agentType,
                target_user_id=target_user_id,
                course_slug=payload.courseSlug,
                lesson_slug=payload.lessonSlug,
            ),
            sort=[("updated_at", -1)],
        )

        if existing:
            if existing.get("status") == "approved":
                return {"message": "Agent request already approved", "data": _serialize_assignment(existing)}

            if existing.get("status") == "pending":
                update_data = {
                    "display_name": payload.displayName or existing.get("display_name") or template["name"],
                    "notes": payload.notes,
                    "updated_at": now,
                }
                await agent_assignments_collection.update_one({"_id": existing["_id"]}, {"$set": update_data})
                existing.update(update_data)
                return {"message": "Agent request already pending", "data": _serialize_assignment(existing)}

            update_data = {
                "requested_by": current_user.get("role"),
                "display_name": payload.displayName or existing.get("display_name") or template["name"],
                "notes": payload.notes,
                "status": "pending" if request_needs_approval else "approved",
                "admin_notes": "",
                "approved_by": None if request_needs_approval else current_user["_id"],
                "approved_at": None if request_needs_approval else now,
                "updated_at": now,
            }
            await agent_assignments_collection.update_one({"_id": existing["_id"]}, {"$set": update_data})
            existing.update(update_data)
            return {"message": "Agent request resubmitted", "data": _serialize_assignment(existing)}

        document = {
            "user_id": current_user["_id"],
            "requested_by": current_user.get("role"),
            "target_user_id": target_user_id,
            "agent_type": payload.agentType,
            "display_name": payload.displayName or template["name"],
            "notes": payload.notes,
            "course_slug": payload.courseSlug,
            "lesson_slug": payload.lessonSlug,
            "status": "pending" if request_needs_approval else "approved",
            "admin_notes": "",
            "approved_by": None if request_needs_approval else current_user["_id"],
            "approved_at": None if request_needs_approval else now,
            "created_at": now,
            "updated_at": now,
        }
        result = await agent_assignments_collection.insert_one(document)
        document["_id"] = result.inserted_id
        return {"message": "Agent request submitted", "data": _serialize_assignment(document)}

    @staticmethod
    async def list_assignments(current_user: dict, status_filter: Optional[str] = None):
        query = {}
        if current_user.get("role") != "Admin":
            query["user_id"] = current_user["_id"]
        if status_filter:
            query["status"] = status_filter

        assignments = []
        cursor = agent_assignments_collection.find(query).sort("updated_at", -1)
        async for assignment in cursor:
            assignments.append(_serialize_assignment(assignment))

        return {"message": "Agent assignments fetched", "data": assignments}

    @staticmethod
    async def update_request_status(assignment_id: str, payload: AgentApprovalUpdate, current_user: dict):
        assignment = await _get_assignment_or_404(assignment_id)
        now = datetime.utcnow()
        update_data = {
            "status": payload.status,
            "admin_notes": payload.adminNotes or "",
            "updated_at": now,
            "approved_by": current_user["_id"] if payload.status == "approved" else None,
            "approved_at": now if payload.status == "approved" else None,
        }
        await agent_assignments_collection.update_one({"_id": assignment["_id"]}, {"$set": update_data})
        assignment.update(update_data)
        return {"message": "Agent request updated", "data": _serialize_assignment(assignment)}

    @staticmethod
    async def create_thread(payload: AgentThreadCreate, current_user: dict):
        assignment = await _get_assignment_or_404(payload.assignmentId)
        _ensure_assignment_access(current_user, assignment)
        if assignment.get("status") != "approved":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={"message": "This agent request has not been approved yet"},
            )

        now = datetime.utcnow()
        thread = {
            "assignment_id": assignment["_id"],
            "user_id": assignment["user_id"],
            "agent_type": assignment["agent_type"],
            "title": payload.title or AGENT_TEMPLATES[assignment["agent_type"]]["defaultTitle"],
            "context": {
                "courseSlug": payload.courseSlug or assignment.get("course_slug"),
                "lessonSlug": payload.lessonSlug or assignment.get("lesson_slug"),
            },
            "last_message_preview": "",
            "created_at": now,
            "updated_at": now,
        }
        result = await agent_threads_collection.insert_one(thread)
        thread["_id"] = result.inserted_id

        if payload.initialMessage:
            await AgentService.post_message(str(thread["_id"]), AgentMessageCreate(message=payload.initialMessage), current_user)

        return {"message": "Agent thread created", "data": _serialize_thread(thread, assignment=assignment)}

    @staticmethod
    async def list_threads(current_user: dict, assignment_id: Optional[str] = None):
        query = {}
        if current_user.get("role") != "Admin":
            query["user_id"] = current_user["_id"]
        if assignment_id:
            query["assignment_id"] = validate_object_id(assignment_id)

        threads = []
        cursor = agent_threads_collection.find(query).sort("updated_at", -1)
        async for thread in cursor:
            assignment = await agent_assignments_collection.find_one({"_id": thread["assignment_id"]})
            threads.append(_serialize_thread(thread, assignment=assignment))

        return {"message": "Agent threads fetched", "data": threads}

    @staticmethod
    async def list_artifacts(current_user: dict, assignment_id: Optional[str] = None):
        query = {}
        if current_user.get("role") != "Admin":
            query["user_id"] = current_user["_id"]
        if assignment_id:
            query["assignment_id"] = validate_object_id(assignment_id)

        artifacts = []
        cursor = agent_artifacts_collection.find(query).sort("created_at", -1)
        async for artifact in cursor:
            artifacts.append(_serialize_artifact(artifact))

        return {"message": "Agent artifacts fetched", "data": artifacts}

    @staticmethod
    async def run_action(assignment_id: str, payload: AgentActionCreate, current_user: dict):
        assignment = await _get_assignment_or_404(assignment_id)
        _ensure_assignment_access(current_user, assignment)
        if assignment.get("status") != "approved":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={"message": "This agent request has not been approved yet"},
            )
        run = await _start_agent_run(
            assignment,
            run_type="action",
            current_user=current_user,
            payload={
                "actionType": payload.actionType,
                "courseSlug": payload.courseSlug,
                "lessonSlug": payload.lessonSlug,
                "targetUserId": payload.targetUserId,
            },
        )
        try:
            graph_result = await AgentGraphRuntime.run_action(assignment, payload, current_user)
            artifact = graph_result.get("artifact")
            if not artifact:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail={"message": "The agent could not complete this action with the current context"},
                )

            serialized = _serialize_artifact(artifact)
            await _finish_agent_run(
                run["_id"],
                status_value="completed",
                steps=graph_result.get("steps", []),
                output={"artifactId": serialized["id"], "artifactType": serialized["artifactType"]},
            )
            return {"message": "Agent action completed", "data": serialized}
        except HTTPException as exc:
            await _finish_agent_run(
                run["_id"],
                status_value="failed",
                error_message=str(exc.detail),
            )
            raise
        except Exception as exc:
            await _finish_agent_run(
                run["_id"],
                status_value="failed",
                error_message=str(exc),
            )
            raise

    @staticmethod
    async def get_thread(thread_id: str, current_user: dict):
        thread = await _get_thread_or_404(thread_id)
        _ensure_thread_access(current_user, thread)
        assignment = await agent_assignments_collection.find_one({"_id": thread["assignment_id"]})
        messages = []
        cursor = agent_messages_collection.find({"thread_id": thread["_id"]}).sort("created_at", 1)
        async for message in cursor:
            messages.append(_serialize_message(message))

        return {
            "message": "Agent thread fetched",
            "data": {
                "thread": _serialize_thread(thread, assignment=assignment),
                "messages": messages,
            },
        }

    @staticmethod
    async def post_message(thread_id: str, payload: AgentMessageCreate, current_user: dict):
        thread = await _get_thread_or_404(thread_id)
        _ensure_thread_access(current_user, thread)
        assignment = await agent_assignments_collection.find_one({"_id": thread["assignment_id"]})
        if not assignment or assignment.get("status") != "approved":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={"message": "This agent is not approved for chat yet"},
            )

        user_message = await _store_message(thread["_id"], "user", payload.message)
        history = await _fetch_recent_messages(thread["_id"])
        run = await _start_agent_run(
            assignment,
            run_type="chat",
            current_user=current_user,
            thread=thread,
            payload={
                "message": payload.message,
                "courseSlug": payload.courseSlug,
                "lessonSlug": payload.lessonSlug,
            },
        )
        try:
            graph_result = await AgentGraphRuntime.run_chat(
                assignment,
                thread,
                payload,
                current_user,
                history,
            )
            ai_reply = graph_result.get("reply") or {
                "content": _fallback_reply(assignment["agent_type"], payload.message, {}),
                "metadata": {"provider": "deveda-fallback", "orchestrator": "langgraph"},
            }

            assistant_message = await _store_message(thread["_id"], "assistant", ai_reply["content"], ai_reply["metadata"])
            await agent_threads_collection.update_one(
                {"_id": thread["_id"]},
                {"$set": {"updated_at": datetime.utcnow(), "last_message_preview": ai_reply["content"][:180]}},
            )
            await _finish_agent_run(
                run["_id"],
                status_value="completed",
                steps=graph_result.get("steps", []),
                output={
                    "assistantMessageId": str(assistant_message["_id"]),
                    "artifactCount": len((ai_reply.get("metadata") or {}).get("artifacts", [])),
                },
            )
        except HTTPException as exc:
            await _finish_agent_run(
                run["_id"],
                status_value="failed",
                error_message=str(exc.detail),
            )
            raise
        except Exception as exc:
            await _finish_agent_run(
                run["_id"],
                status_value="failed",
                error_message=str(exc),
            )
            raise

        return {
            "message": "Agent response created",
            "data": {
                "userMessage": _serialize_message(user_message),
                "assistantMessage": _serialize_message(assistant_message),
            },
        }
