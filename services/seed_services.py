# app/services/seed_services.py
from datetime import datetime
from bson import ObjectId
from database.database import course_catalog_collection, user_profiles_collection, user_courses_collection

COURSE_CATALOG_DEFAULTS = [
    {
        "slug": "frontend-development-beginner",
        "title": "Frontend Development Beginner",
        "description": "Start with HTML, CSS, and basic JavaScript while building your first responsive web pages.",
        "category": "Frontend Development",
        "difficulty": "Beginner",
        "duration": 240,
        "total_quizzes": 4,
        "total_lessons": 12,
        "instructor": "Deveda Frontend Team",
        "prerequisites": [],
        "tags": ["html", "css", "javascript", "responsive-design"],
        "thumbnail": "",
    },
    {
        "slug": "frontend-development-foundations",
        "title": "Frontend Development Foundations",
        "description": "Build confidence with HTML, CSS, and JavaScript through component-driven page projects.",
        "category": "Frontend Development",
        "difficulty": "Beginner",
        "duration": 300,
        "total_quizzes": 5,
        "total_lessons": 14,
        "instructor": "Deveda Frontend Team",
        "prerequisites": ["frontend-development-beginner"],
        "tags": ["html", "css", "javascript", "dom"],
        "thumbnail": "",
    },
    {
        "slug": "frontend-development-intermediate",
        "title": "Frontend Development Intermediate",
        "description": "Move from core web fundamentals into richer JavaScript patterns and an introduction to React.",
        "category": "Frontend Development",
        "difficulty": "Intermediate",
        "duration": 360,
        "total_quizzes": 6,
        "total_lessons": 16,
        "instructor": "Deveda Frontend Team",
        "prerequisites": ["frontend-development-foundations"],
        "tags": ["html", "css", "javascript", "react"],
        "thumbnail": "",
    },
    {
        "slug": "frontend-development-advanced",
        "title": "Frontend Development Advanced",
        "description": "Ship production-ready interfaces with React, Next.js, Tailwind CSS, JavaScript, and TypeScript.",
        "category": "Frontend Development",
        "difficulty": "Advanced",
        "duration": 480,
        "total_quizzes": 8,
        "total_lessons": 20,
        "instructor": "Deveda Frontend Team",
        "prerequisites": ["frontend-development-intermediate"],
        "tags": ["react", "nextjs", "tailwind", "javascript", "typescript"],
        "thumbnail": "",
    },
    {
        "slug": "frontend-development-mastery",
        "title": "Frontend Development Mastery",
        "description": "Operate like a frontend engineer by mastering architecture, performance, accessibility, and delivery.",
        "category": "Frontend Development",
        "difficulty": "Mastery",
        "duration": 540,
        "total_quizzes": 10,
        "total_lessons": 24,
        "instructor": "Deveda Frontend Team",
        "prerequisites": ["frontend-development-advanced"],
        "tags": ["frontend-engineering", "performance", "accessibility", "architecture"],
        "thumbnail": "",
    },
    {
        "slug": "backend-development-python-apis",
        "title": "Backend Development: Introduction to Python and APIs",
        "description": "Learn Python fundamentals and how HTTP APIs work before building your first backend service.",
        "category": "Backend Development",
        "difficulty": "Beginner",
        "duration": 260,
        "total_quizzes": 4,
        "total_lessons": 12,
        "instructor": "Deveda Backend Team",
        "prerequisites": [],
        "tags": ["python", "http", "rest", "apis"],
        "thumbnail": "",
    },
    {
        "slug": "backend-development-fastapi",
        "title": "Backend Development: FastAPI",
        "description": "Use FastAPI to build validated, documented, and testable APIs with Python.",
        "category": "Backend Development",
        "difficulty": "Intermediate",
        "duration": 320,
        "total_quizzes": 5,
        "total_lessons": 14,
        "instructor": "Deveda Backend Team",
        "prerequisites": ["backend-development-python-apis"],
        "tags": ["python", "fastapi", "pydantic", "api-design"],
        "thumbnail": "",
    },
    {
        "slug": "backend-development-intermediate",
        "title": "Backend Development Intermediate",
        "description": "Add authentication, persistence, background work, and better service structure to your backend systems.",
        "category": "Backend Development",
        "difficulty": "Intermediate",
        "duration": 400,
        "total_quizzes": 6,
        "total_lessons": 18,
        "instructor": "Deveda Backend Team",
        "prerequisites": ["backend-development-fastapi"],
        "tags": ["authentication", "databases", "background-jobs", "testing"],
        "thumbnail": "",
    },
    {
        "slug": "backend-development-advanced",
        "title": "Backend Development Advanced",
        "description": "Design scalable services with observability, reliability, security, and performance in mind.",
        "category": "Backend Development",
        "difficulty": "Advanced",
        "duration": 500,
        "total_quizzes": 8,
        "total_lessons": 22,
        "instructor": "Deveda Backend Team",
        "prerequisites": ["backend-development-intermediate"],
        "tags": ["architecture", "security", "performance", "observability"],
        "thumbnail": "",
    },
    {
        "slug": "systems-design-essentials",
        "title": "Systems Design Essentials",
        "description": "Understand tradeoffs in designing reliable, scalable systems with queues, caches, databases, and APIs.",
        "category": "Systems Design",
        "difficulty": "Advanced",
        "duration": 420,
        "total_quizzes": 6,
        "total_lessons": 16,
        "instructor": "Deveda Architecture Team",
        "prerequisites": ["backend-development-intermediate"],
        "tags": ["systems-design", "scalability", "distributed-systems", "architecture"],
        "thumbnail": "",
    },
]

ROLE_DEFAULTS = {
    "Admin": {
        "courses": [],
    },
    "Student": {
        "courses": [
            {"slug": "frontend-development-beginner", "category": "Frontend Development", "difficulty": "Beginner"},
            {"slug": "frontend-development-foundations", "category": "Frontend Development", "difficulty": "Beginner"},
            {"slug": "backend-development-python-apis", "category": "Backend Development", "difficulty": "Beginner"},
            {"slug": "backend-development-fastapi", "category": "Backend Development", "difficulty": "Intermediate"},
        ],
    },
    "Instructor": {
        "courses": [],
    },
}


async def ensure_course_catalog_seeded():
    for course in COURSE_CATALOG_DEFAULTS:
        existing = await course_catalog_collection.find_one({"slug": course["slug"]})
        if existing:
            continue

        await course_catalog_collection.insert_one({
            **course,
            "created_at": datetime.utcnow(),
        })

async def seed_user_data(user_id: ObjectId, role: str):
    defaults = ROLE_DEFAULTS.get(role, ROLE_DEFAULTS["Student"])

    # Create user profile
    await user_profiles_collection.insert_one({
        "user_id": user_id,
        "role": role,
        "registered_courses": [course["slug"] for course in defaults["courses"]],
        "created_at": datetime.utcnow(),
    })

    # Enroll in default courses
    for course in defaults["courses"]:
        await user_courses_collection.insert_one({
            "user_id": user_id,
            "course_slug": course["slug"],
            "category": course["category"],
            "difficulty": course["difficulty"],
            "progress": 0,
            "completed": False,
            "last_accessed": None,
            "enrolled_at": datetime.utcnow(),
        })

