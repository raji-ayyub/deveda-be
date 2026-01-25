# app/services/seed_services.py
from datetime import datetime
from bson import ObjectId
from database.database import (
    user_profiles_collection,
    user_courses_collection,
    game_progress_collection
)

ROLE_DEFAULTS = {
    "User": {
        "courses": [
            {"slug": "intro_python", "category": "Programming", "difficulty": "Beginner"},
            {"slug": "basic_math", "category": "Mathematics", "difficulty": "Beginner"}
        ],
        "games": ["math_blaster"],
    },
    "Student": {
        "courses": [
            {"slug": "intro_python", "category": "Programming", "difficulty": "Beginner"},
            {"slug": "basic_math", "category": "Mathematics", "difficulty": "Beginner"},
            {"slug": "web_dev_basics", "category": "Web Development", "difficulty": "Intermediate"}
        ],
        "games": ["math_blaster", "code_quest"],
    },
    "Instructor": {
        "courses": [
            {"slug": "advanced_python", "category": "Programming", "difficulty": "Advanced"},
            {"slug": "machine_learning", "category": "Data Science", "difficulty": "Advanced"}
        ],
        "games": [],
    },
}

async def seed_user_data(user_id: ObjectId, role: str):
    defaults = ROLE_DEFAULTS.get(role, ROLE_DEFAULTS["User"])

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

    # Initialize game progress
    for game in defaults["games"]:
        await game_progress_collection.insert_one({
            "user_id": user_id,
            "game_id": game,
            "level": 1,
            "xp": 0,
            "last_played": None,
        })