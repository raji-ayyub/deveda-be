import hashlib
import os
import time

from fastapi import HTTPException, status

from schemas.schemas import MediaUploadSignatureRequest

CLOUDINARY_CLOUD_NAME = os.getenv("CLOUDINARY_CLOUD_NAME", "")
CLOUDINARY_API_KEY = os.getenv("CLOUDINARY_API_KEY", "")
CLOUDINARY_API_SECRET = os.getenv("CLOUDINARY_API_SECRET", "")


def _build_signature(params: dict) -> str:
    signature_base = "&".join(f"{key}={params[key]}" for key in sorted(params))
    return hashlib.sha1(f"{signature_base}{CLOUDINARY_API_SECRET}".encode("utf-8")).hexdigest()


class MediaService:
    @staticmethod
    async def create_upload_signature(current_user: dict, payload: MediaUploadSignatureRequest):
        if not CLOUDINARY_CLOUD_NAME or not CLOUDINARY_API_KEY or not CLOUDINARY_API_SECRET:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail={"message": "Cloudinary is not configured on the server"},
            )

        asset_type = payload.assetType
        if asset_type == "course" and current_user.get("role") not in {"Admin", "Instructor"}:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={"message": "Only admins and instructors can upload course images"},
            )

        timestamp = int(time.time())
        folder = f"deveda/{asset_type}s"
        if asset_type == "profile":
            folder = f"{folder}/{current_user['_id']}"

        params = {
            "folder": folder,
            "timestamp": timestamp,
        }
        if payload.publicId:
            params["public_id"] = payload.publicId

        signature = _build_signature(params)
        return {
            "message": "Cloudinary signature generated",
            "data": {
                "cloudName": CLOUDINARY_CLOUD_NAME,
                "apiKey": CLOUDINARY_API_KEY,
                "folder": folder,
                "timestamp": timestamp,
                "signature": signature,
                "publicId": payload.publicId,
            },
        }
