# app/db/db.py
from motor.motor_asyncio import AsyncIOMotorClient
import os
from dotenv import load_dotenv

load_dotenv()

MONGO_URI = os.getenv("MONGO_URI")
DB_NAME = os.getenv("DB_NAME")

client = AsyncIOMotorClient(MONGO_URI)
if DB_NAME:
    db = client[DB_NAME]

users_collection = db.users
admins_collection = db.admins
user_profiles_collection = db.user_profiles
user_courses_collection = db.user_courses
quiz_progress_collection = db.quiz_progress
quiz_questions_collection = db.quiz_questions
course_catalog_collection = db.course_catalog
course_curricula_collection = db.course_curricula
achievements_collection = db.achievements
agent_assignments_collection = db.agent_assignments
agent_threads_collection = db.agent_threads
agent_messages_collection = db.agent_messages
agent_artifacts_collection = db.agent_artifacts
