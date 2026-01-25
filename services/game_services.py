# app/services/game_services.py
from fastapi import HTTPException
from datetime import datetime
from bson import ObjectId
from database.database import game_progress_collection
from services.auth_services import validate_object_id

def serialize_game(game: dict) -> dict:
    return {
        "id": str(game["_id"]),
        "userId": str(game["user_id"]),
        "gameId": game["game_id"],
        "level": game["level"],
        "xp": game["xp"],
        "lastPlayed": game["last_played"],
    }

class GameService:
    
    @staticmethod
    async def get_game_progress(user_id: str):
        oid = validate_object_id(user_id)

        games = []
        async for g in game_progress_collection.find({"user_id": oid}):
            games.append(serialize_game(g))

        return {
            "message": "Game progress fetched",
            "data": games,
        }
    
    @staticmethod
    async def update_game_progress(user_id: str, game_id: str, level: int, xp: int):
        oid = validate_object_id(user_id)

        game = await game_progress_collection.find_one({
            "user_id": oid,
            "game_id": game_id
        })

        if not game:
            # Create new game progress entry
            game_data = {
                "user_id": oid,
                "game_id": game_id,
                "level": level,
                "xp": xp,
                "last_played": datetime.utcnow(),
            }
            result = await game_progress_collection.insert_one(game_data)
            game_data["_id"] = result.inserted_id
            
            return {
                "message": "Game progress created",
                "data": serialize_game(game_data),
            }
        else:
            # Update existing game progress
            await game_progress_collection.update_one(
                {"_id": game["_id"]},
                {"$set": {
                    "level": level,
                    "xp": xp,
                    "last_played": datetime.utcnow(),
                }}
            )
            
            updated_game = await game_progress_collection.find_one({"_id": game["_id"]})
            
            return {
                "message": "Game progress updated",
                "data": serialize_game(updated_game),
            }