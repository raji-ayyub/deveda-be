from datetime import datetime

from bson import ObjectId
from fastapi import HTTPException, status

from database.database import quiz_progress_collection, quiz_questions_collection, user_courses_collection
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
        quizzes = []
        quiz_ids = await quiz_questions_collection.distinct("quiz_id")
        for quiz_id in sorted(quiz_ids):
            question_count = await quiz_questions_collection.count_documents({"quiz_id": quiz_id, "is_active": True})
            quizzes.append(
                {
                    "id": quiz_id,
                    "title": quiz_id.replace("-", " ").replace("_", " ").title(),
                    "totalQuestions": question_count,
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
        attempts = []
        cursor = quiz_progress_collection.find({"user_id": oid}).sort("attempted_at", -1)
        async for attempt in cursor:
            attempts.append(serialize_quiz_attempt(attempt))
        return {"message": "Quiz attempts fetched", "data": attempts}
