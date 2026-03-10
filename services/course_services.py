# app/services/course_services.py
from fastapi import HTTPException, Query
from datetime import datetime
from typing import Optional, List
from bson import ObjectId
from database.database import (
    course_catalog_collection, 
    user_courses_collection,
    user_profiles_collection,
    users_collection
)
from schemas.schemas import CourseEnroll, CourseCatalogCreate, CourseProgressUpdate
from services.auth_services import validate_object_id, serialize_user
from services.achievement_services import AchievementService
from services.seed_services import ensure_course_catalog_seeded

CODING_CATEGORIES = {"Frontend Development", "Backend Development", "Systems Design"}

def serialize_course(course: dict) -> dict:
    return {
        "id": str(course["_id"]),
        "userId": str(course["user_id"]),
        "courseSlug": course["course_slug"],
        "category": course.get("category", "General"),
        "difficulty": course.get("difficulty", "Beginner"),
        "progress": course["progress"],
        "completed": course["completed"],
        "lastAccessed": course["last_accessed"],
        "enrolledAt": course.get("enrolled_at"),
    }

def serialize_course_catalog(course: dict) -> dict:
    return {
        "id": str(course["_id"]),
        "slug": course["slug"],
        "title": course["title"],
        "description": course["description"],
        "category": course["category"],
        "difficulty": course["difficulty"],
        "duration": course.get("duration", 0),
        "totalQuizzes": course.get("total_quizzes", 0),
        "totalLessons": course.get("total_lessons", 0),
        "instructor": course.get("instructor", ""),
        "prerequisites": course.get("prerequisites", []),
        "tags": course.get("tags", []),
        "thumbnail": course.get("thumbnail", ""),
        "thumbnailPublicId": course.get("thumbnail_public_id", ""),
        "createdAt": course.get("created_at"),
    }

class CourseService:
    
    @staticmethod
    async def enroll_course(user_id: str, payload: CourseEnroll):
        oid = validate_object_id(user_id)
        await ensure_course_catalog_seeded()

        # Check if course exists in catalog
        catalog_course = await course_catalog_collection.find_one({"slug": payload.courseSlug})
        if not catalog_course or catalog_course.get("category") not in CODING_CATEGORIES:
            raise HTTPException(404, {"message": "Course not found in catalog"})

        existing = await user_courses_collection.find_one({
            "user_id": oid,
            "course_slug": payload.courseSlug,
        })

        if existing:
            raise HTTPException(400, {"message": "Already enrolled in this course"})

        course = {
            "user_id": oid,
            "course_slug": payload.courseSlug,
            "category": catalog_course.get("category", payload.category),
            "difficulty": catalog_course.get("difficulty", payload.difficulty),
            "progress": 0,
            "completed": False,
            "last_accessed": datetime.utcnow(),
            "enrolled_at": datetime.utcnow(),
        }

        result = await user_courses_collection.insert_one(course)
        course["_id"] = result.inserted_id

        await user_profiles_collection.update_one(
            {"user_id": oid},
            {"$addToSet": {"registered_courses": payload.courseSlug}},
        )

        return {
            "message": "Course enrolled successfully",
            "data": serialize_course(course),
        }
    
    @staticmethod
    async def get_user_courses(user_id: str):
        oid = validate_object_id(user_id)

        courses = []
        async for c in user_courses_collection.find({"user_id": oid}):
            if c.get("category") in CODING_CATEGORIES:
                courses.append(serialize_course(c))

        return {
            "message": "User courses fetched",
            "data": courses,
        }
    
    @staticmethod
    async def get_user_course_progress(user_id: str, course_slug: str):
        """Get a user's progress for a specific course"""
        oid = validate_object_id(user_id)
        
        course = await user_courses_collection.find_one({
            "user_id": oid,
            "course_slug": course_slug,
        })
        
        if not course:
            raise HTTPException(404, {"message": "Course enrollment not found"})
        if course.get("category") not in CODING_CATEGORIES:
            raise HTTPException(404, {"message": "Course enrollment not found"})
        
        # Get course details from catalog
        catalog_course = await course_catalog_collection.find_one({"slug": course_slug})
        
        return {
            "message": "User course progress fetched",
            "data": {
                "progress": serialize_course(course),
                "course_details": serialize_course_catalog(catalog_course) if catalog_course else None,
            },
        }
    
    @staticmethod
    async def update_course_progress(user_id: str, course_slug: str, payload: CourseProgressUpdate):
        oid = validate_object_id(user_id)

        course = await user_courses_collection.find_one({
            "user_id": oid,
            "course_slug": course_slug
        })

        if not course:
            raise HTTPException(404, {"message": "Course enrollment not found"})

        update_data = {
            "progress": payload.progress,
            "last_accessed": datetime.utcnow(),
        }
        
        if payload.completed is not None:
            update_data["completed"] = payload.completed

        await user_courses_collection.update_one(
            {"_id": course["_id"]},
            {"$set": update_data}
        )

        updated_course = await user_courses_collection.find_one({"_id": course["_id"]})
        awarded = await AchievementService.sync_course_achievements(
            oid,
            course_slug,
            int(updated_course.get("progress", 0)),
            bool(updated_course.get("completed", False)),
        )

        return {
            "message": "Course progress updated",
            "data": {
                "course": serialize_course(updated_course),
                "awards": awarded,
            },
        }

class CourseCatalogService:
    
    @staticmethod
    async def create_course_catalog(payload: CourseCatalogCreate):
        existing = await course_catalog_collection.find_one({"slug": payload.slug})
        if existing:
            raise HTTPException(400, {"message": "Course with this slug already exists"})

        course = {
            "slug": payload.slug,
            "title": payload.title,
            "description": payload.description,
            "category": payload.category,
            "difficulty": payload.difficulty,
            "duration": payload.duration,
            "total_quizzes": payload.totalQuizzes,
            "total_lessons": payload.totalLessons,
            "instructor": payload.instructor,
            "prerequisites": payload.prerequisites,
            "tags": payload.tags,
            "thumbnail": payload.thumbnail,
            "thumbnail_public_id": payload.thumbnailPublicId,
            "created_at": datetime.utcnow(),
        }

        result = await course_catalog_collection.insert_one(course)
        course["_id"] = result.inserted_id

        return {
            "message": "Course added to catalog successfully",
            "data": serialize_course_catalog(course),
        }
    
    @staticmethod
    async def get_course_catalog(
        category: Optional[str] = None,
        difficulty: Optional[str] = None,
        search: Optional[str] = None
    ):
        await ensure_course_catalog_seeded()
        query = {"category": {"$in": list(CODING_CATEGORIES)}}
        
        if category:
            query["category"] = category
        if difficulty:
            query["difficulty"] = difficulty
        if search:
            query["$or"] = [
                {"title": {"$regex": search, "$options": "i"}},
                {"description": {"$regex": search, "$options": "i"}},
                {"tags": {"$regex": search, "$options": "i"}},
            ]

        courses = []
        async for c in course_catalog_collection.find(query):
            courses.append(serialize_course_catalog(c))

        return {
            "message": "Course catalog fetched",
            "data": courses,
        }
    
    @staticmethod
    async def get_course_by_slug(slug: str):
        """Get a single course by its slug"""
        await ensure_course_catalog_seeded()
        course = await course_catalog_collection.find_one({"slug": slug})
        if not course or course.get("category") not in CODING_CATEGORIES:
            raise HTTPException(404, {"message": "Course not found"})
        
        return {
            "message": "Course fetched successfully",
            "data": serialize_course_catalog(course),
        }
    
    @staticmethod
    async def update_course_catalog(slug: str, payload: CourseCatalogCreate):
        """Update a course in the catalog"""
        existing_course = await course_catalog_collection.find_one({"slug": slug})
        if not existing_course:
            raise HTTPException(404, {"message": "Course not found"})
        
        # Don't allow changing the slug
        if payload.slug != slug:
            raise HTTPException(400, {"message": "Cannot change course slug"})
        
        update_data = {
            "title": payload.title,
            "description": payload.description,
            "category": payload.category,
            "difficulty": payload.difficulty,
            "duration": payload.duration,
            "total_quizzes": payload.totalQuizzes,
            "total_lessons": payload.totalLessons,
            "instructor": payload.instructor,
            "prerequisites": payload.prerequisites,
            "tags": payload.tags,
            "thumbnail": payload.thumbnail,
            "thumbnail_public_id": payload.thumbnailPublicId,
            "updated_at": datetime.utcnow(),
        }
        
        await course_catalog_collection.update_one(
            {"slug": slug},
            {"$set": update_data}
        )
        
        updated_course = await course_catalog_collection.find_one({"slug": slug})
        
        return {
            "message": "Course updated successfully",
            "data": serialize_course_catalog(updated_course),
        }
    
    @staticmethod
    async def delete_course_catalog(slug: str):
        """Delete a course from the catalog"""
        result = await course_catalog_collection.delete_one({"slug": slug})
        
        if result.deleted_count == 0:
            raise HTTPException(404, {"message": "Course not found"})
        
        # Also delete any user enrollments for this course
        await user_courses_collection.delete_many({"course_slug": slug})
        
        # Remove from user profiles
        await user_profiles_collection.update_many(
            {"registered_courses": slug},
            {"$pull": {"registered_courses": slug}}
        )
        
        return {
            "message": "Course deleted successfully",
            "data": None,
        }
    
    @staticmethod
    async def get_course_catalog_stats():
        """Get statistics about the course catalog"""
        await ensure_course_catalog_seeded()
        catalog_query = {"category": {"$in": list(CODING_CATEGORIES)}}
        total_courses = await course_catalog_collection.count_documents(catalog_query)
        
        # Count total enrollments
        total_enrollments = await user_courses_collection.count_documents({})
        
        # Count unique enrolled users
        unique_users = len(await user_courses_collection.distinct("user_id"))
        
        # Get most popular courses by enrollment count
        pipeline = [
            {"$group": {"_id": "$course_slug", "count": {"$sum": 1}}},
            {"$sort": {"count": -1}},
            {"$limit": 5}
        ]
        popular_courses = await user_courses_collection.aggregate(pipeline).to_list(None)
        
        # Get category distribution
        category_pipeline = [
            {"$match": catalog_query},
            {"$group": {"_id": "$category", "count": {"$sum": 1}}},
            {"$sort": {"count": -1}}
        ]
        categories = await course_catalog_collection.aggregate(category_pipeline).to_list(None)
        
        # Get difficulty distribution
        difficulty_pipeline = [
            {"$match": catalog_query},
            {"$group": {"_id": "$difficulty", "count": {"$sum": 1}}},
            {"$sort": {"count": -1}}
        ]
        difficulties = await course_catalog_collection.aggregate(difficulty_pipeline).to_list(None)
        
        return {
            "message": "Course catalog statistics",
            "data": {
                "total_courses": total_courses,
                "total_enrollments": total_enrollments,
                "unique_enrolled_users": unique_users,
                "popular_courses": popular_courses,
                "categories": categories,
                "difficulties": difficulties,
            },
        }
    
    @staticmethod
    async def get_course_enrollments(course_slug: str, limit: int = Query(10, ge=1, le=100)):
        """Get recent enrollments for a course"""
        catalog_course = await course_catalog_collection.find_one({"slug": course_slug})
        if not catalog_course or catalog_course.get("category") not in CODING_CATEGORIES:
            raise HTTPException(404, {"message": "Course not found"})

        enrollments = []
        
        # Get recent enrollments with user info
        pipeline = [
            {"$match": {"course_slug": course_slug}},
            {"$sort": {"enrolled_at": -1}},
            {"$limit": limit},
            {
                "$lookup": {
                    "from": "users",
                    "localField": "user_id",
                    "foreignField": "_id",
                    "as": "user"
                }
            },
            {"$unwind": "$user"},
        ]
        
        async for enrollment in user_courses_collection.aggregate(pipeline):
            enrollments.append({
                "id": str(enrollment["_id"]),
                "user": serialize_user(enrollment["user"]),
                "progress": enrollment["progress"],
                "completed": enrollment["completed"],
                "enrolled_at": enrollment["enrolled_at"],
                "last_accessed": enrollment.get("last_accessed"),
            })
        
        total_enrollments = await user_courses_collection.count_documents({"course_slug": course_slug})
        
        return {
            "message": "Course enrollments fetched",
            "data": {
                "enrollments": enrollments,
                "total": total_enrollments,
            },
        }
