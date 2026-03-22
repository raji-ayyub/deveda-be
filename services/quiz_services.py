from datetime import datetime

from bson import ObjectId
from fastapi import HTTPException, status

from database.database import course_curricula_collection, quiz_progress_collection, quiz_questions_collection, user_courses_collection, users_collection
from schemas.schemas import QuestionCreate, QuizAttemptCreate
from services.achievement_services import AchievementService
from services.auth_services import validate_object_id


def serialize_question(question: dict, include_answer: bool = True) -> dict:
    data = {
        "id": str(question["_id"]),
        "quizId": question["quiz_id"],
        "question": question["question"],
        "options": question["options"],
        "explanation": question.get("explanation", ""),
        "points": question.get("points", 1),
        "questionType": question.get("question_type", "multiple_choice"),
        "timeLimit": question.get("time_limit", 60),
        "difficulty": question.get("difficulty", "Medium"),
        "isActive": question.get("is_active", True),
        "createdAt": question.get("created_at"),
        "updatedAt": question.get("updated_at", question.get("created_at")),
        "createdBy": question.get("created_by", "Deveda Team"),
    }
    if include_answer:
        data["correctAnswer"] = question["correct_answer"]
    return data


def serialize_quiz_attempt(attempt: dict) -> dict:
    return {
        "id": str(attempt["_id"]),
        "userId": str(attempt["user_id"]),
        "quizId": attempt["quiz_id"],
        "courseSlug": attempt.get("course_slug"),
        "score": attempt["score"],
        "passed": attempt["passed"],
        "attemptedAt": attempt["attempted_at"],
    }


def _fallback_quiz_title(quiz_id: str) -> str:
    return quiz_id.replace("-", " ").replace("_", " ").title()


async def _quiz_catalog_metadata() -> dict[str, dict[str, str | None]]:
    metadata: dict[str, dict[str, str | None]] = {}
    cursor = course_curricula_collection.find({}, {"course_slug": 1, "modules": 1})
    async for curriculum in cursor:
        course_slug = curriculum.get("course_slug")
        for module in curriculum.get("modules", []):
            assessment_quiz_id = str(module.get("assessmentQuizId") or "").strip()
            if assessment_quiz_id and assessment_quiz_id not in metadata:
                metadata[assessment_quiz_id] = {
                    "title": str(module.get("assessmentTitle") or "").strip() or _fallback_quiz_title(assessment_quiz_id),
                    "courseSlug": course_slug,
                }

            for lesson in module.get("lessons", []):
                lesson_quiz_id = str(lesson.get("quizId") or "").strip()
                if lesson_quiz_id and lesson_quiz_id not in metadata:
                    lesson_title = str(lesson.get("quizTitle") or "").strip() or f"{str(lesson.get('title') or 'Lesson').strip()} assessment"
                    metadata[lesson_quiz_id] = {
                        "title": lesson_title,
                        "courseSlug": course_slug,
                    }
    return metadata


async def ensure_student_account(user_id: ObjectId) -> dict:
    user = await users_collection.find_one({"_id": user_id})
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"message": "User not found"},
        )
    if user.get("role", "Student") != "Student":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"message": "Quiz attempts are only available to student accounts"},
        )
    return user


class QuizService:
    @staticmethod
    async def create_question(payload: QuestionCreate, created_by: str = "Deveda Team"):
        now = datetime.utcnow()
        question = {
            "quiz_id": payload.quizId,
            "question": payload.question,
            "options": payload.options,
            "correct_answer": payload.correctAnswer,
            "explanation": payload.explanation,
            "points": payload.points,
            "question_type": payload.questionType,
            "difficulty": payload.difficulty,
            "is_active": payload.isActive,
            "time_limit": payload.timeLimit,
            "created_by": created_by,
            "created_at": now,
            "updated_at": now,
        }

        result = await quiz_questions_collection.insert_one(question)
        question["_id"] = result.inserted_id

        return {"message": "Question created successfully", "data": serialize_question(question)}

    @staticmethod
    async def update_question(question_id: str, payload: QuestionCreate):
        oid = validate_object_id(question_id)
        existing = await quiz_questions_collection.find_one({"_id": oid})
        if not existing:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"message": "Question not found"},
            )

        update_data = {
            "quiz_id": payload.quizId,
            "question": payload.question,
            "options": payload.options,
            "correct_answer": payload.correctAnswer,
            "explanation": payload.explanation,
            "points": payload.points,
            "question_type": payload.questionType,
            "difficulty": payload.difficulty,
            "is_active": payload.isActive,
            "time_limit": payload.timeLimit,
            "updated_at": datetime.utcnow(),
        }

        await quiz_questions_collection.update_one({"_id": oid}, {"$set": update_data})
        updated = await quiz_questions_collection.find_one({"_id": oid})
        return {"message": "Question updated successfully", "data": serialize_question(updated)}

    @staticmethod
    async def delete_question(question_id: str):
        oid = validate_object_id(question_id)
        result = await quiz_questions_collection.delete_one({"_id": oid})
        if result.deleted_count == 0:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"message": "Question not found"},
            )

        return {"message": "Question deleted successfully", "data": True}

    @staticmethod
    async def get_question_bank():
        questions = []
        cursor = quiz_questions_collection.find().sort("updated_at", -1)
        async for question in cursor:
            questions.append(serialize_question(question))
        return {"message": "Question bank fetched", "data": questions}

    @staticmethod
    async def get_quizzes():
        metadata = await _quiz_catalog_metadata()
        quizzes = []
        quiz_ids = await quiz_questions_collection.distinct("quiz_id")
        for quiz_id in sorted(quiz_ids, key=lambda item: (metadata.get(item, {}).get("title") or _fallback_quiz_title(item)).lower()):
            question_count = 0
            duration = 0
            async for question in quiz_questions_collection.find({"quiz_id": quiz_id, "is_active": True}, {"time_limit": 1}):
                question_count += 1
                duration += int(question.get("time_limit") or 0)
            quiz_meta = metadata.get(quiz_id, {})
            quizzes.append(
                {
                    "id": quiz_id,
                    "title": quiz_meta.get("title") or _fallback_quiz_title(quiz_id),
                    "courseSlug": quiz_meta.get("courseSlug"),
                    "totalQuestions": question_count,
                    "duration": duration,
                }
            )
        return {"message": "Quizzes fetched", "data": quizzes}

    @staticmethod
    async def get_quiz_questions(quiz_id: str):
        questions = []
        async for question in quiz_questions_collection.find({"quiz_id": quiz_id, "is_active": True}):
            questions.append(serialize_question(question))
        return {"message": "Quiz questions fetched", "data": questions}

    @staticmethod
    async def get_all_quiz_questions():
        questions = []
        async for question in quiz_questions_collection.find({"is_active": True}):
            questions.append(serialize_question(question, include_answer=False))
        return {"message": "All quiz questions fetched", "data": questions}

    @staticmethod
    async def submit_quiz_attempt(user_id: str, payload: QuizAttemptCreate):
        oid = validate_object_id(user_id)
        await ensure_student_account(oid)
        passed = payload.score >= 60
        awarded = []

        attempt = {
            "user_id": oid,
            "quiz_id": payload.quizId,
            "course_slug": payload.courseSlug,
            "score": payload.score,
            "passed": passed,
            "attempted_at": datetime.utcnow(),
        }

        if passed and payload.courseSlug:
            course = await user_courses_collection.find_one({"user_id": oid, "course_slug": payload.courseSlug})
            if course:
                new_progress = min(course.get("progress", 0) + 10, 100)
                completed = new_progress >= 100

                await user_courses_collection.update_one(
                    {"_id": course["_id"]},
                    {
                        "$set": {
                            "progress": new_progress,
                            "completed": completed,
                            "last_accessed": datetime.utcnow(),
                        }
                    },
                )
                awarded = await AchievementService.sync_course_achievements(
                    oid,
                    payload.courseSlug,
                    new_progress,
                    completed,
                )

        result = await quiz_progress_collection.insert_one(attempt)
        attempt["_id"] = result.inserted_id
        return {
            "message": "Quiz attempt recorded",
            "data": {
                "attempt": serialize_quiz_attempt(attempt),
                "awards": awarded,
            },
        }

    @staticmethod
    async def get_user_quiz_attempts(user_id: str):
        oid = validate_object_id(user_id)
        await ensure_student_account(oid)
        attempts = []
        cursor = quiz_progress_collection.find({"user_id": oid}).sort("attempted_at", -1)
        async for attempt in cursor:
            attempts.append(serialize_quiz_attempt(attempt))
        return {"message": "Quiz attempts fetched", "data": attempts}
