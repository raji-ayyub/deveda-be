from fastapi import FastAPI, HTTPException, status
from pydantic import BaseModel, EmailStr, Field
from typing import Optional, List
from bson import ObjectId
import hashlib
from fastapi.middleware.cors import CORSMiddleware


from database.database import users_collection

app = FastAPI(title="User Auth API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)



# ------------------------
# Utilities
# ------------------------

def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


def verify_password(plain: str, hashed: str) -> bool:
    return hash_password(plain) == hashed


def serialize_user(user: dict) -> dict:
    return {
        "id": str(user["_id"]),
        "email": user["email"],
        "firstName": user.get("first_name"),
        "lastName": user.get("last_name"),
        "role": user.get("role", "User"),
        "isActive": user.get("is_active", True),
    }


def validate_object_id(user_id: str) -> ObjectId:
    if not ObjectId.is_valid(user_id):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"message": "Invalid user ID"},
        )
    return ObjectId(user_id)


# ------------------------
# Schemas
# ------------------------

class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=6)
    firstName: str
    lastName: str
    role: str = Field(default="User")


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class UserUpdate(BaseModel):
    email: EmailStr
    firstName: str
    lastName: str
    role: str
    isActive: bool


class UserPatch(BaseModel):
    email: Optional[EmailStr] = None
    firstName: Optional[str] = None
    lastName: Optional[str] = None
    role: Optional[str] = None
    isActive: Optional[bool] = None


# ------------------------
# Routes
# ------------------------

@app.post("/register", status_code=status.HTTP_201_CREATED)
async def register_user(payload: UserCreate):
    existing = await users_collection.find_one({"email": payload.email})
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"message": "Email already registered"},
        )

    user = {
        "email": payload.email,
        "password": hash_password(payload.password),
        "first_name": payload.firstName,
        "last_name": payload.lastName,
        "role": payload.role,
        "is_active": True,
    }

    result = await users_collection.insert_one(user)
    user["_id"] = result.inserted_id

    return {
        "message": "User registered successfully",
        "data": serialize_user(user),
    }


@app.post("/login")
async def login_user(payload: UserLogin):
    user = await users_collection.find_one({"email": payload.email})

    if not user or not verify_password(payload.password, user["password"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"message": "Invalid email or password"},
        )

    return {
        "message": "Login successful",
        "data": {
            "user": serialize_user(user)
        },
    }


@app.get("/users")
async def get_all_users():
    users = []
    async for user in users_collection.find():
        users.append(serialize_user(user))

    return {
        "message": "Users fetched successfully",
        "data": users,
    }


@app.get("/users/{user_id}")
async def get_user(user_id: str):
    oid = validate_object_id(user_id)

    user = await users_collection.find_one({"_id": oid})
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"message": "User not found"},
        )

    return {
        "message": "User fetched successfully",
        "data": serialize_user(user),
    }


@app.put("/users/{user_id}")
async def update_user(user_id: str, payload: UserUpdate):
    oid = validate_object_id(user_id)

    result = await users_collection.update_one(
        {"_id": oid},
        {
            "$set": {
                "email": payload.email,
                "first_name": payload.firstName,
                "last_name": payload.lastName,
                "role": payload.role,
                "is_active": payload.isActive,
            }
        },
    )

    if result.matched_count == 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"message": "User not found"},
        )

    user = await users_collection.find_one({"_id": oid})

    return {
        "message": "User updated successfully",
        "data": serialize_user(user),
    }


@app.patch("/users/{user_id}")
async def patch_user(user_id: str, payload: UserPatch):
    oid = validate_object_id(user_id)

    update_data = {}

    if payload.email is not None:
        update_data["email"] = payload.email
    if payload.firstName is not None:
        update_data["first_name"] = payload.firstName
    if payload.lastName is not None:
        update_data["last_name"] = payload.lastName
    if payload.role is not None:
        update_data["role"] = payload.role
    if payload.isActive is not None:
        update_data["is_active"] = payload.isActive

    if not update_data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"message": "No fields provided for update"},
        )

    result = await users_collection.update_one(
        {"_id": oid},
        {"$set": update_data},
    )

    if result.matched_count == 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"message": "User not found"},
        )

    user = await users_collection.find_one({"_id": oid})

    return {
        "message": "User updated successfully",
        "data": serialize_user(user),
    }


@app.delete("/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(user_id: str):
    oid = validate_object_id(user_id)

    result = await users_collection.delete_one({"_id": oid})

    if result.deleted_count == 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"message": "User not found"},
        )
