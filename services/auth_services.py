import hashlib
import os
from datetime import datetime, timedelta
from typing import Optional, Set

import bcrypt
import jwt
from bson import ObjectId
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from passlib.hash import pbkdf2_sha256

from database.database import (
    quiz_progress_collection,
    user_courses_collection,
    user_profiles_collection,
    users_collection,
)
from schemas.schemas import (
    PUBLIC_REGISTRATION_ROLES,
    PasswordChangeRequest,
    PrivateAdminCreateRequest,
    UserCreate,
    UserLogin,
    UserPatch,
    UserStatusUpdate,
    UserUpdate,
)
from services.seed_services import initialize_user_profile

auth_scheme = HTTPBearer(auto_error=False)
JWT_SECRET = os.getenv("JWT_SECRET") or os.getenv("SECRET_KEY") or "deveda-local-dev-secret"
JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "10080"))
ADMIN_SETUP_SECRET = os.getenv("ADMIN_SETUP_SECRET", "")


def hash_password(password: str) -> str:
    return pbkdf2_sha256.hash(password)


def is_managed_password_hash(hashed: str) -> bool:
    return pbkdf2_sha256.identify(hashed) or hashed.startswith("$2")


def needs_password_rehash(hashed: str) -> bool:
    return not pbkdf2_sha256.identify(hashed)


def verify_password(plain: str, hashed: str) -> bool:
    if pbkdf2_sha256.identify(hashed):
        return pbkdf2_sha256.verify(plain, hashed)
    if hashed.startswith("$2"):
        try:
            return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
        except ValueError:
            return False
    return hashlib.sha256(plain.encode("utf-8")).hexdigest() == hashed


def validate_object_id(user_id: str) -> ObjectId:
    if not ObjectId.is_valid(user_id):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"message": "Invalid user ID"},
        )
    return ObjectId(user_id)


def create_access_token(user: dict) -> str:
    payload = {
        "sub": str(user["_id"]),
        "role": user.get("role", "Student"),
        "exp": datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def serialize_user(user: dict) -> dict:
    return {
        "id": str(user["_id"]),
        "email": user["email"],
        "firstName": user.get("first_name"),
        "lastName": user.get("last_name"),
        "role": user.get("role", "Student"),
        "isActive": user.get("is_active", True),
        "avatarUrl": user.get("avatar_url", ""),
        "avatarPublicId": user.get("avatar_public_id", ""),
        "createdAt": user.get("created_at"),
        "lastLogin": user.get("last_login"),
    }


def serialize_profile(profile: dict) -> dict:
    return {
        "id": str(profile["_id"]),
        "userId": str(profile["user_id"]),
        "role": profile["role"],
        "registeredCourses": profile["registered_courses"],
        "createdAt": profile["created_at"],
    }


def build_auth_response(user: dict, message: str) -> dict:
    return {
        "message": message,
        "data": {
            "user": serialize_user(user),
            "accessToken": create_access_token(user),
        },
    }


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(auth_scheme),
) -> dict:
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"message": "Authentication required"},
        )

    try:
        payload = jwt.decode(credentials.credentials, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except jwt.PyJWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"message": "Invalid or expired session"},
        ) from exc

    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"message": "Invalid session payload"},
        )

    user = await users_collection.find_one({"_id": validate_object_id(user_id)})
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"message": "User not found for this session"},
        )
    if not user.get("is_active", True):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"message": "Your account is inactive"},
        )

    return user


async def get_optional_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(auth_scheme),
) -> Optional[dict]:
    if credentials is None:
        return None
    return await get_current_user(credentials)


def require_roles(*roles: str):
    allowed = {role.title() for role in roles}

    async def dependency(current_user: dict = Depends(get_current_user)) -> dict:
        if current_user.get("role", "Student") not in allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={"message": "You do not have permission to perform this action"},
            )
        return current_user

    return dependency


def ensure_self_or_roles(current_user: dict, user_id: str, allowed_roles: Optional[Set[str]] = None) -> None:
    if str(current_user["_id"]) == user_id:
        return

    allowed = allowed_roles or {"Admin"}
    if current_user.get("role", "Student") not in allowed:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"message": "You do not have permission to access this resource"},
        )


async def _apply_user_updates(oid: ObjectId, update_data: dict) -> dict:
    result = await users_collection.update_one({"_id": oid}, {"$set": update_data})
    if result.matched_count == 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"message": "User not found"},
        )

    if "role" in update_data:
        await user_profiles_collection.update_one(
            {"user_id": oid},
            {"$set": {"role": update_data["role"]}},
        )

    user = await users_collection.find_one({"_id": oid})
    return serialize_user(user)


async def _ensure_unique_email(email: str, excluded_user_id: Optional[ObjectId] = None) -> None:
    query = {"email": email}
    if excluded_user_id is not None:
        query["_id"] = {"$ne": excluded_user_id}
    if await users_collection.find_one(query):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"message": "Email already registered"},
        )


class AuthService:
    @staticmethod
    async def register_user(payload: UserCreate):
        if payload.role not in PUBLIC_REGISTRATION_ROLES:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={"message": "Public registration is currently limited to student and instructor accounts"},
            )

        await _ensure_unique_email(payload.email)

        now = datetime.utcnow()
        user = {
            "email": payload.email,
            "password": hash_password(payload.password),
            "first_name": payload.firstName,
            "last_name": payload.lastName,
            "role": payload.role,
            "is_active": True,
            "avatar_url": "",
            "avatar_public_id": "",
            "created_at": now,
            "last_login": now,
        }

        result = await users_collection.insert_one(user)
        user["_id"] = result.inserted_id

        await initialize_user_profile(user["_id"], user["role"])

        return build_auth_response(user, "Account created successfully")

    @staticmethod
    async def register_private_admin(payload: PrivateAdminCreateRequest):
        if not ADMIN_SETUP_SECRET:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail={"message": "Private admin setup is not configured on the server"},
            )

        if payload.adminSetupSecret != ADMIN_SETUP_SECRET:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={"message": "Invalid admin setup secret"},
            )

        await _ensure_unique_email(payload.email)

        now = datetime.utcnow()
        user = {
            "email": payload.email,
            "password": hash_password(payload.password),
            "first_name": payload.firstName,
            "last_name": payload.lastName,
            "role": "Admin",
            "is_active": True,
            "avatar_url": "",
            "avatar_public_id": "",
            "created_at": now,
            "last_login": now,
        }

        result = await users_collection.insert_one(user)
        user["_id"] = result.inserted_id

        await initialize_user_profile(user["_id"], user["role"])

        return build_auth_response(user, "Admin account created successfully")

    @staticmethod
    async def login_user(payload: UserLogin):
        user = await users_collection.find_one({"email": payload.email})

        if not user or not verify_password(payload.password, user["password"]):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={"message": "Invalid email or password"},
            )

        if not user.get("is_active", True):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={"message": "Your account is inactive"},
            )

        if needs_password_rehash(user["password"]):
            await users_collection.update_one(
                {"_id": user["_id"]},
                {"$set": {"password": hash_password(payload.password)}},
            )

        user["last_login"] = datetime.utcnow()
        await users_collection.update_one(
            {"_id": user["_id"]},
            {"$set": {"last_login": user["last_login"]}},
        )

        return build_auth_response(user, "Login successful")

    @staticmethod
    async def get_session(current_user: dict):
        return {
            "message": "Current session fetched",
            "data": serialize_user(current_user),
        }

    @staticmethod
    async def change_password(current_user: dict, payload: PasswordChangeRequest):
        if not verify_password(payload.currentPassword, current_user["password"]):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"message": "Current password is incorrect"},
            )

        if payload.currentPassword == payload.newPassword:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"message": "New password must be different from your current password"},
            )

        await users_collection.update_one(
            {"_id": current_user["_id"]},
            {"$set": {"password": hash_password(payload.newPassword)}},
        )

        return {"message": "Password updated successfully", "data": True}


class UserService:
    @staticmethod
    async def create_user(payload: UserCreate):
        await _ensure_unique_email(payload.email)

        now = datetime.utcnow()
        user = {
            "email": payload.email,
            "password": hash_password(payload.password),
            "first_name": payload.firstName,
            "last_name": payload.lastName,
            "role": payload.role,
            "is_active": True,
            "avatar_url": "",
            "avatar_public_id": "",
            "created_at": now,
            "last_login": None,
        }

        result = await users_collection.insert_one(user)
        user["_id"] = result.inserted_id

        await initialize_user_profile(user["_id"], payload.role)

        return {"message": "User created successfully", "data": serialize_user(user)}

    @staticmethod
    async def get_all_users():
        users = []
        cursor = users_collection.find().sort("created_at", -1)
        async for user in cursor:
            users.append(
                {
                    **serialize_user(user),
                    "coursesCount": await user_courses_collection.count_documents({"user_id": user["_id"]}),
                    "quizAttempts": await quiz_progress_collection.count_documents({"user_id": user["_id"]}),
                }
            )

        return {"message": "Users fetched successfully", "data": users}

    @staticmethod
    async def get_user(user_id: str):
        oid = validate_object_id(user_id)
        user = await users_collection.find_one({"_id": oid})
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"message": "User not found"},
            )

        profile = await user_profiles_collection.find_one({"user_id": oid})
        courses_count = await user_courses_collection.count_documents({"user_id": oid})
        quiz_attempts = await quiz_progress_collection.count_documents({"user_id": oid})

        return {
            "message": "User fetched successfully",
            "data": {
                "user": serialize_user(user),
                "profile": serialize_profile(profile) if profile else None,
                "stats": {
                    "coursesCount": courses_count,
                    "quizAttempts": quiz_attempts,
                },
            },
        }

    @staticmethod
    async def update_user(user_id: str, payload: UserUpdate, current_user: dict):
        oid = validate_object_id(user_id)
        ensure_self_or_roles(current_user, user_id, {"Admin"})
        await _ensure_unique_email(payload.email, excluded_user_id=oid)

        update_data = {
            "email": payload.email,
            "first_name": payload.firstName,
            "last_name": payload.lastName,
        }
        if payload.avatarUrl is not None:
            update_data["avatar_url"] = payload.avatarUrl
        if payload.avatarPublicId is not None:
            update_data["avatar_public_id"] = payload.avatarPublicId

        if str(current_user["_id"]) == user_id and current_user.get("role") != "Admin":
            update_data["is_active"] = current_user.get("is_active", True)
            update_data["role"] = current_user.get("role", "Student")
        else:
            update_data["is_active"] = payload.isActive
            update_data["role"] = payload.role

        return {
            "message": "User updated successfully",
            "data": await _apply_user_updates(oid, update_data),
        }

    @staticmethod
    async def patch_user(user_id: str, payload: UserPatch, current_user: dict):
        oid = validate_object_id(user_id)
        ensure_self_or_roles(current_user, user_id, {"Admin"})

        update_data = {}

        if payload.email is not None:
            await _ensure_unique_email(payload.email, excluded_user_id=oid)
            update_data["email"] = payload.email
        if payload.firstName is not None:
            update_data["first_name"] = payload.firstName
        if payload.lastName is not None:
            update_data["last_name"] = payload.lastName
        if payload.avatarUrl is not None:
            update_data["avatar_url"] = payload.avatarUrl
        if payload.avatarPublicId is not None:
            update_data["avatar_public_id"] = payload.avatarPublicId
        if payload.role is not None:
            if current_user.get("role") != "Admin":
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail={"message": "Only admins can change account roles"},
                )
            update_data["role"] = payload.role
        if payload.isActive is not None:
            if current_user.get("role") != "Admin":
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail={"message": "Only admins can change account status"},
                )
            update_data["is_active"] = payload.isActive

        if not update_data:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"message": "No fields provided for update"},
            )

        return {
            "message": "User updated successfully",
            "data": await _apply_user_updates(oid, update_data),
        }

    @staticmethod
    async def update_user_status(user_id: str, payload: UserStatusUpdate):
        oid = validate_object_id(user_id)
        return {
            "message": "User status updated successfully",
            "data": await _apply_user_updates(oid, {"is_active": payload.isActive}),
        }

    @staticmethod
    async def delete_user(user_id: str, current_user: dict):
        oid = validate_object_id(user_id)
        ensure_self_or_roles(current_user, user_id, {"Admin"})

        result = await users_collection.delete_one({"_id": oid})
        if result.deleted_count == 0:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"message": "User not found"},
            )

        await user_profiles_collection.delete_many({"user_id": oid})
        await user_courses_collection.delete_many({"user_id": oid})
        await quiz_progress_collection.delete_many({"user_id": oid})

        return {"message": "User deleted successfully", "data": True}
