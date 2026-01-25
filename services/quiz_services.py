# app/services/quiz_services.py
from fastapi import HTTPException
from datetime import datetime
from typing import List
from bson import ObjectId
from database.database import (
    quiz_questions_collection,
    quiz_progress_collection,
    user_courses_collection
)
from schemas.schemas import QuizAttemptCreate, QuestionCreate
from services.auth_services import validate_object_id

def serialize_question(question: dict) -> dict:
    return {
        "id": str(question["_id"]),
        "quizId": question["quiz_id"],
        "question": question["question"],
        "options": question["options"],
        "correctAnswer": question["correct_answer"],
        "explanation": question.get("explanation", ""),
        "points": question.get("points", 1),
        "questionType": question.get("question_type", "multiple_choice"),
    }

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
    async def create_question(quiz_id: str, payload: QuestionCreate):
        question = {
            "quiz_id": quiz_id,
            "question": payload.question,
            "options": payload.options,
            "correct_answer": payload.correctAnswer,
            "explanation": payload.explanation,
            "points": payload.points,
            "question_type": payload.questionType,
            "created_at": datetime.utcnow(),
        }

        result = await quiz_questions_collection.insert_one(question)
        question["_id"] = result.inserted_id

        return {
            "message": "Question created successfully",
            "data": serialize_question(question),
        }
    
    @staticmethod
    async def get_quiz_questions(quiz_id: str):
        questions = []
        async for q in quiz_questions_collection.find({"quiz_id": quiz_id}):
            # Don't send correct answer to client for security
            q_data = serialize_question(q)
            q_data.pop("correctAnswer", None)
            questions.append(q_data)

        return {
            "message": "Quiz questions fetched",
            "data": questions,
        }
    
    @staticmethod
    async def get_all_quiz_questions():
        """Fetch all quiz questions in the system (admin or analytics use)."""
        questions = []
        cursor = quiz_questions_collection.find()
        
        async for q in cursor:
            questions.append(serialize_question(q))
        
        return {
            "message": "All quiz questions fetched",
            "data": questions,
        }
    
    @staticmethod
    async def submit_quiz_attempt(user_id: str, payload: QuizAttemptCreate):
        oid = validate_object_id(user_id)
        
        passed = payload.score >= 60

        attempt = {
            "user_id": oid,
            "quiz_id": payload.quizId,
            "course_slug": payload.courseSlug,
            "score": payload.score,
            "passed": passed,
            "attempted_at": datetime.utcnow(),
        }

        # Auto-update course progress if quiz is passed and course slug is provided
        if passed and payload.courseSlug:
            # Get current course progress
            course = await user_courses_collection.find_one({
                "user_id": oid,
                "course_slug": payload.courseSlug
            })
            
            if course:
                # Calculate new progress (increase by 10% for each passed quiz, max 100%)
                new_progress = min(course.get("progress", 0) + 10, 100)
                completed = new_progress >= 100
                
                await user_courses_collection.update_one(
                    {"_id": course["_id"]},
                    {"$set": {
                        "progress": new_progress,
                        "completed": completed,
                        "last_accessed": datetime.utcnow(),
                    }}
                )
                
                # Also update attempt with course info
                attempt["progress_increment"] = 10
                attempt["new_progress"] = new_progress

        result = await quiz_progress_collection.insert_one(attempt)
        attempt["_id"] = result.inserted_id

        return {
            "message": "Quiz attempt recorded" + (" and progress updated" if passed and payload.courseSlug else ""),
            "data": serialize_quiz_attempt(attempt),
        }
    
    @staticmethod
    async def get_user_quiz_attempts(user_id: str):
        oid = validate_object_id(user_id)

        attempts = []
        async for a in quiz_progress_collection.find({"user_id": oid}):
            attempts.append(serialize_quiz_attempt(a))

        return {
            "message": "Quiz attempts fetched",
            "data": attempts,
        }