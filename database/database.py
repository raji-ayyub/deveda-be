# app/db/db.py
from motor.motor_asyncio import AsyncIOMotorClient
import os
from dotenv import load_dotenv

load_dotenv()


MONGO_URI = os.getenv("MONGO_URI")
# print(MONGO_URI)
DB_NAME = os.getenv("DB_NAME")


client = AsyncIOMotorClient(MONGO_URI)
if DB_NAME:
    db = client[DB_NAME]

users_collection = db.users
doctors_collection = db.doctors
admins_collection = db.admins