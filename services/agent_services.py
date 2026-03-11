import json
import os
import re
from datetime import datetime
from typing import Any, Optional
from urllib import error, request

from bson import ObjectId
from fastapi import HTTPException, status

from database.database import (
    achievements_collection,
    agent_assignments_collection,
    agent_artifacts_collection,
    agent_messages_collection,
    agent_threads_collection,
    course_catalog_collection,
    course_curricula_collection,
    quiz_progress_collection,
    user_courses_collection,
    users_collection,
)
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
        "name": "Lesson Tutor",
        "description": "Explains lesson material in a side chat with examples, stories, and step-by-step guidance.",
        "allowedRequesterRoles": ["Student", "Instructor"],
        "requiresApproval": True,
        "defaultTitle": "Lesson Tutor Chat",
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


def _actor_label(user: dict) -> str:
    return f"{user.get('first_name', '')} {user.get('last_name', '')}".strip() or user.get("email", "Deveda Agent")


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
    result = await agent_artifacts_collection.insert_one(document)
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
            f"Let us work through `{lesson['title']}` from `{course['title']}` in a calm way.\n\n"
            f"Lesson focus: {lesson.get('summary', 'This lesson builds one core skill step by step.')} "
            f"Think of it like learning to ride a bicycle: first you see the balance, then you try one small push, then you repeat until it feels natural.\n\n"
            f"Here is the teaching pattern I recommend:\n"
            f"1. Explain the idea in plain language.\n"
            f"2. Show one small example.\n"
            f"3. Ask the learner to change one part of that example.\n"
            f"4. Connect the lesson back to the bigger course project.\n\n"
            f"If you send the exact concept you want explained, I will teach it with an example and a simple story."
        )

    if course:
        return (
            f"I am ready to tutor inside `{course['title']}`. Ask me about any concept, and I will explain it with examples, analogies, and a gentle step-by-step path.\n\n"
            f"If the learner is stuck, I can switch to simpler wording first, then rebuild toward the formal explanation."
        )

    return (
        "I can teach the current lesson through examples, stories, and short checkpoints. Ask a question like 'Explain props like I am 12' or 'Show me a simple example with code and why it works.'"
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
    return CourseCurriculumUpsert(
        overview=payload.get("overview", ""),
        modules=payload.get("modules", []),
        milestoneProjects=payload.get("milestoneProjects", payload.get("milestone_projects", [])),
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
    if payload.artifactId:
        artifact = await _get_artifact_or_404(payload.artifactId)
        if str(artifact.get("assignment_id")) != str(assignment["_id"]):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={"message": "This artifact does not belong to the selected agent assignment"},
            )
        if artifact.get("artifact_type") != "curriculum_draft":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"message": "Only curriculum draft artifacts can be applied to a live course"},
            )
        return artifact

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
        return "You are Deveda's Lesson Tutor agent. Teach clearly, kindly, and concretely. Use the provided lesson and course context before answering."
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
    if not OPENAI_API_KEY:
        return None

    payload = {
        "model": OPENAI_MODEL,
        "messages": _build_openai_messages(agent_type, context, history, user_message),
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


async def _create_lesson_content_suggestion_artifact(
    assignment: dict,
    context: dict,
    instruction: str,
    *,
    thread_id: Optional[ObjectId] = None,
) -> Optional[dict]:
    course = context.get("course")
    lesson = context.get("lesson")
    if not course or not lesson:
        return None

    module_title = lesson.get("moduleTitle", "Module")
    category = course.get("category", "Frontend Development")
    tailored_markdown = "\n".join(
        [
            f"# {lesson['title']}",
            "",
            "## Why this lesson matters",
            lesson.get("summary", ""),
            "",
            "## Instructor walkthrough",
            f"Open with a concrete {category.lower()} example that makes the idea in **{lesson['title']}** visible right away.",
            "Move from explanation to demonstration, then let the learner make one guided change before independent practice.",
            "",
            "## Teaching checkpoints",
            "1. Clarify the concept in simple language.",
            "2. Show the smallest useful implementation.",
            "3. Ask the learner what would break if one part changed.",
            "4. Use the practice task or playground before closing the lesson.",
            "",
            "## Common learner friction",
            "Watch for learners repeating steps without understanding why they work. Pause and ask them to predict the next outcome before they run the code.",
        ]
    )
    suggestion = normalize_lesson(
        course,
        module_title,
        {
            **lesson,
            "learningObjectives": [
                f"Describe the main idea behind {lesson['title']} with confidence.",
                "Apply the concept in one guided coding task.",
                "Explain one mistake or misunderstanding to avoid.",
            ],
            "keyTakeaways": [
                lesson.get("summary", "Understand the lesson clearly."),
                "Use a small working example before adding extra complexity.",
                "Practice by changing one thing intentionally and observing the result.",
            ],
            "contentMarkdown": tailored_markdown,
            "practicePrompt": (
                f"Create a small working example for **{lesson['title']}**, then change one important part and explain what effect that change had."
            ),
            "instructorNotes": (
                f"Agent suggestion: keep this lesson grounded in practical {category.lower()} decisions and ask the learner to narrate their thinking while they work."
            ),
        },
    )

    payload = {
        "courseSlug": course["slug"],
        "lessonSlug": lesson["slug"],
        "moduleTitle": module_title,
        "lesson": suggestion,
        "guidance": [
            "Start with one concrete example before giving definitions.",
            "Use the playground or practice prompt before moving to the next lesson.",
            "Check understanding by asking the learner to explain the change they made.",
        ],
        "instruction": instruction,
    }
    summary = f"Prepared a richer lesson content suggestion for {lesson['title']} in {course['title']}."
    return await _store_artifact(
        assignment,
        "lesson_content_suggestion",
        f"{lesson['title']} lesson suggestion",
        summary,
        payload,
        thread_id=thread_id,
        route=f"/instructor/dashboard/cms?course={course['slug']}",
    )


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
        document = {
            "user_id": current_user["_id"],
            "requested_by": current_user.get("role"),
            "target_user_id": target_user_id,
            "agent_type": payload.agentType,
            "display_name": payload.displayName or template["name"],
            "notes": payload.notes,
            "course_slug": payload.courseSlug,
            "lesson_slug": payload.lessonSlug,
            "status": "approved" if current_user.get("role") == "Admin" else "pending",
            "admin_notes": "",
            "approved_by": current_user["_id"] if current_user.get("role") == "Admin" else None,
            "approved_at": now if current_user.get("role") == "Admin" else None,
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

        context_payload = AgentMessageCreate(
            message=payload.instruction or payload.actionType,
            courseSlug=payload.courseSlug or assignment.get("course_slug"),
            lessonSlug=payload.lessonSlug or assignment.get("lesson_slug"),
        )
        context, _ = await _build_context_bundle(assignment, context_payload)

        artifact = None
        if payload.actionType == "create_course_shell":
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
        elif payload.actionType == "save_planning_note":
            if payload.targetUserId:
                context.update(await _collect_progress_context(validate_object_id(payload.targetUserId)))
            artifact = await _create_planning_note_artifact(assignment, context, payload.instruction or "")

        if not artifact:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"message": "The agent could not complete this action with the current context"},
            )

        return {"message": "Agent action completed", "data": _serialize_artifact(artifact)}

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
        context, tools_used = await _build_context_bundle(assignment, payload)
        artifacts: list[dict] = []

        if assignment["agent_type"] == "course_builder" and _supports_curriculum_draft_request(payload.message):
            artifact = await _create_curriculum_draft_artifact(assignment, context, payload.message, thread_id=thread["_id"])
            if artifact:
                artifacts.append(_serialize_artifact(artifact))

        if assignment["agent_type"] == "progress_analyst" and _supports_planning_note_request(payload.message):
            artifact = await _create_planning_note_artifact(assignment, context, payload.message, thread_id=thread["_id"])
            if artifact:
                artifacts.append(_serialize_artifact(artifact))

        controlled_reply = None
        if assignment["agent_type"] == "course_builder":
            controlled_reply = await _build_controlled_course_builder_reply(
                assignment,
                payload.message,
                context,
                history,
                thread["_id"],
                current_user,
            )

        ai_reply = controlled_reply or _call_openai(assignment["agent_type"], context, history, payload.message)

        if ai_reply is None:
            ai_reply = {
                "content": _fallback_reply(assignment["agent_type"], payload.message, context),
                "metadata": {"provider": "deveda-fallback", "toolsUsed": tools_used},
            }
        else:
            ai_reply["metadata"]["toolsUsed"] = tools_used

        if artifacts:
            ai_reply["metadata"]["artifacts"] = artifacts
            if len(artifacts) == 1:
                ai_reply["content"] += f"\n\nI also created: {artifacts[0]['title']}."

        navigation = _platform_navigation_reply(payload.message, context) if assignment["agent_type"] == "platform_support" else None
        if navigation and "route" not in ai_reply["metadata"]:
            best_area = None
            message_tokens = _token_set(payload.message)
            for area in context.get("areas", []):
                if len(_token_set(f"{area['name']} {area['description']}") & message_tokens) > 0:
                    best_area = area
                    break
            if best_area:
                ai_reply["metadata"]["route"] = best_area["route"]
                ai_reply["metadata"]["routeLabel"] = f"Open {best_area['name']}"

        assistant_message = await _store_message(thread["_id"], "assistant", ai_reply["content"], ai_reply["metadata"])
        await agent_threads_collection.update_one(
            {"_id": thread["_id"]},
            {"$set": {"updated_at": datetime.utcnow(), "last_message_preview": ai_reply["content"][:180]}},
        )

        return {
            "message": "Agent response created",
            "data": {
                "userMessage": _serialize_message(user_message),
                "assistantMessage": _serialize_message(assistant_message),
            },
        }
