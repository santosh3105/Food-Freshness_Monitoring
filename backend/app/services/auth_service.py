import logging
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
from bson import ObjectId
from fastapi import HTTPException, status
from backend.app.database import get_users_collection
from backend.app.models.user_model import UserRole, user_helper, normalize_role
from backend.app.schemas.user_schema import UserRegisterRequest, UserLoginRequest
from backend.app.utils.security import hash_password, verify_password, create_access_token
from backend.app.services.audit_service import AuditService

logger = logging.getLogger("uvicorn.error")


class AuthService:
    @staticmethod
    def register_user(data: UserRegisterRequest) -> Dict[str, Any]:
        try:
            users_col = get_users_collection()
        except Exception as exc:
            logger.error("Failed to connect to users collection for registration: %s", exc)
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Database service unavailable. Please ensure MongoDB Atlas is connected."
            )

        if users_col is None:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Database service unavailable. Please ensure MongoDB is running."
            )

        clean_email = data.email.lower().strip()

        # Check existing user
        try:
            existing_user = users_col.find_one({"email": clean_email})
        except Exception as exc:
            logger.error("Failed to query user for registration: %s", exc)
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Database query error during registration. Please try again."
            )

        if existing_user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email is already registered. Please login or use a different email."
            )

        # Hash password securely
        hashed_pwd = hash_password(data.password)

        now = datetime.now(timezone.utc)
        user_doc = {
            "name": data.name.strip(),
            "email": clean_email,
            "password_hash": hashed_pwd,
            "role": data.role,
            "status": "active",
            "is_active": True,
            "auth_provider": "local",
            "last_login": None,
            "created_at": now,
            "updated_at": now,
        }

        try:
            result = users_col.insert_one(user_doc)
            created_user = users_col.find_one({"_id": result.inserted_id})
        except Exception as exc:
            logger.error("Failed to insert user document: %s", exc)
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Failed to create user in database. Please check database permissions."
            )

        # Record audit log
        try:
            AuditService.log_event(
                action="USER_REGISTER",
                actor_id=str(result.inserted_id),
                actor_email=clean_email,
                actor_role=data.role,
                target_id=str(result.inserted_id),
                target_resource="users",
                new_value={"role": data.role, "status": "active"},
                status="success",
            )
        except Exception as log_err:
            logger.warning("Audit log for registration failed: %s", log_err)

        return user_helper(created_user)

    @staticmethod
    def authenticate_user(data: UserLoginRequest) -> Dict[str, Any]:
        try:
            users_col = get_users_collection()
        except Exception as exc:
            logger.error("Failed to connect to users collection for login: %s", exc)
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Database service unavailable. Please verify MongoDB Atlas connectivity."
            )

        if users_col is None:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Database service unavailable. Please ensure MongoDB is running."
            )

        clean_ident = (data.email or data.username or "").lower().strip()
        if not clean_ident:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Email or username is required."
            )

        try:
            user = users_col.find_one({"email": clean_ident})
        except Exception as exc:
            logger.error("Failed to query user for login: %s", exc)
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Database error during authentication. Please try again."
            )

        if not user or not verify_password(data.password, user.get("password_hash", "")):
            try:
                AuditService.log_event(
                    action="USER_LOGIN_FAILED",
                    actor_email=clean_ident,
                    target_resource="users",
                    status="failure",
                    metadata={"reason": "Invalid email or password"},
                )
            except Exception:
                pass
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid email or password. Please verify your credentials."
            )

        # Enforce account activation status
        if user.get("is_active") is False or user.get("status") in ["deactivated", "inactive"]:
            try:
                AuditService.log_event(
                    action="USER_LOGIN_FAILED",
                    actor_id=str(user["_id"]),
                    actor_email=clean_ident,
                    actor_role=user.get("role"),
                    target_id=str(user["_id"]),
                    target_resource="users",
                    status="failure",
                    metadata={"reason": "Account is deactivated"},
                )
            except Exception:
                pass
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Your account has been deactivated. Please contact the administrator."
            )

        now = datetime.now(timezone.utc)
        try:
            users_col.update_one({"_id": user["_id"]}, {"$set": {"last_login": now, "updated_at": now}})
            user["last_login"] = now
        except Exception as update_err:
            logger.warning("Failed to update last_login timestamp: %s", update_err)

        # Record successful login audit
        try:
            AuditService.log_event(
                action="USER_LOGIN",
                actor_id=str(user["_id"]),
                actor_email=clean_ident,
                actor_role=user.get("role"),
                target_id=str(user["_id"]),
                target_resource="users",
                status="success",
            )
        except Exception:
            pass

        # Generate JWT Token
        token_payload = {
            "sub": str(user["_id"]),
            "email": user["email"],
            "role": user.get("role", UserRole.CONSUMER.value),
        }
        access_token = create_access_token(data=token_payload)

        return {
            "access_token": access_token,
            "token_type": "bearer",
            "user": user_helper(user),
        }

    @staticmethod
    def get_user_by_id(user_id: str) -> Dict[str, Any]:
        users_col = get_users_collection()
        if users_col is None:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Database service unavailable."
            )

        try:
            user = users_col.find_one({"_id": ObjectId(user_id)})
        except Exception:
            user = users_col.find_one({"_id": user_id})

        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"User with ID {user_id} not found."
            )
        return user_helper(user)

    @staticmethod
    def list_all_users() -> List[Dict[str, Any]]:
        users_col = get_users_collection()
        if users_col is None:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Database service unavailable."
            )

        users = users_col.find().sort("created_at", -1)
        return [user_helper(u) for u in users]
