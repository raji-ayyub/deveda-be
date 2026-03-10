from datetime import datetime, timedelta

from database.database import (
    course_catalog_collection,
    quiz_progress_collection,
    quiz_questions_collection,
    user_courses_collection,
    users_collection,
)
from services.auth_services import serialize_user


class AdminService:
    @staticmethod
    async def get_stats():
        total_users = await users_collection.count_documents({})
        total_courses = await course_catalog_collection.count_documents({})
        total_questions = await quiz_questions_collection.count_documents({})
        total_quizzes = len(await quiz_questions_collection.distinct("quiz_id"))
        active_users = await users_collection.count_documents({"is_active": True})
        recent_registrations = await users_collection.count_documents(
            {"created_at": {"$gte": datetime.utcnow() - timedelta(days=7)}}
        )

        pipeline = [{"$group": {"_id": None, "avg": {"$avg": "$progress"}}}]
        progress_data = await user_courses_collection.aggregate(pipeline).to_list(length=1)
        average_progress = round(progress_data[0]["avg"], 1) if progress_data else 0

        return {
            "message": "Admin stats fetched",
            "data": {
                "totalUsers": total_users,
                "totalCourses": total_courses,
                "totalQuizzes": total_quizzes,
                "totalQuestions": total_questions,
                "activeUsers": active_users,
                "recentRegistrations": recent_registrations,
                "averageProgress": average_progress,
            },
        }

    @staticmethod
    async def get_recent_activity(limit: int = 12):
        activity = []

        recent_users = await users_collection.find().sort("created_at", -1).to_list(length=4)
        for user in recent_users:
            activity.append(
                {
                    "id": f"user-{user['_id']}",
                    "userId": str(user["_id"]),
                    "userName": f"{user.get('first_name', '')} {user.get('last_name', '')}".strip() or user["email"],
                    "action": "joined",
                    "target": "Deveda",
                    "timestamp": user.get("created_at"),
                    "icon": "U",
                }
            )

        recent_enrollments = await user_courses_collection.find().sort("enrolled_at", -1).to_list(length=4)
        for enrollment in recent_enrollments:
            user = await users_collection.find_one({"_id": enrollment["user_id"]})
            if not user:
                continue
            activity.append(
                {
                    "id": f"enrollment-{enrollment['_id']}",
                    "userId": str(user["_id"]),
                    "userName": f"{user.get('first_name', '')} {user.get('last_name', '')}".strip() or user["email"],
                    "action": "enrolled in",
                    "target": enrollment["course_slug"],
                    "timestamp": enrollment.get("enrolled_at"),
                    "icon": "C",
                }
            )

        recent_attempts = await quiz_progress_collection.find().sort("attempted_at", -1).to_list(length=4)
        for attempt in recent_attempts:
            user = await users_collection.find_one({"_id": attempt["user_id"]})
            if not user:
                continue
            activity.append(
                {
                    "id": f"quiz-{attempt['_id']}",
                    "userId": str(user["_id"]),
                    "userName": f"{user.get('first_name', '')} {user.get('last_name', '')}".strip() or user["email"],
                    "action": "completed quiz",
                    "target": attempt["quiz_id"],
                    "timestamp": attempt.get("attempted_at"),
                    "icon": "Q",
                }
            )

        activity.sort(key=lambda item: item.get("timestamp") or datetime.min, reverse=True)
        return {"message": "Recent activity fetched", "data": activity[:limit]}

    @staticmethod
    async def get_chart_data(period: str = "7d"):
        days = 7 if period == "7d" else 30 if period == "30d" else 90
        start_date = datetime.utcnow() - timedelta(days=days - 1)
        labels = []
        data_points = []

        for offset in range(days):
            day = start_date + timedelta(days=offset)
            next_day = day + timedelta(days=1)
            labels.append(day.strftime("%b %d"))
            count = await users_collection.count_documents(
                {"created_at": {"$gte": day, "$lt": next_day}}
            )
            data_points.append(count)

        return {
            "message": "Chart data fetched",
            "data": {
                "labels": labels,
                "datasets": [
                    {
                        "label": "New users",
                        "data": data_points,
                        "backgroundColor": "rgba(37, 99, 235, 0.2)",
                        "borderColor": "rgba(37, 99, 235, 1)",
                        "borderWidth": 2,
                    }
                ],
            },
        }
