from datetime import datetime

from bson import ObjectId

from database.database import user_profiles_collection


async def initialize_user_profile(user_id: ObjectId, role: str) -> None:
    existing = await user_profiles_collection.find_one({"user_id": user_id})
    if existing:
        await user_profiles_collection.update_one(
            {"_id": existing["_id"]},
            {"$set": {"role": role}},
        )
        return

    await user_profiles_collection.insert_one(
        {
            "user_id": user_id,
            "role": role,
            "registered_courses": [],
            "created_at": datetime.utcnow(),
        }
    )
