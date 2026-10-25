from typing import Dict, Any, Optional
from fastapi import APIRouter, Depends, status, Request, HTTPException
from backend.app.schemas.user_schema import (
    UserRegisterRequest,
    UserLoginRequest,
    UserResponse,
    TokenResponse,
)

from backend.app.services.auth_service import AuthService
from backend.app.services.audit_service import AuditService
from backend.app.utils.dependencies import get_current_user, get_current_user_optional

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post(
    "/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new user account"
)
async def register(data: UserRegisterRequest):
    """
    Register a new user in the platform.
    Public registration supports Consumer, Retailer, Warehouse Manager,
    Food Manufacturer, Supply Chain Operator, Food Quality Inspector, and Admin roles.
    """
    new_user = AuthService.register_user(data)
    return new_user


@router.post(
    "/login",
    response_model=TokenResponse,
    summary="Authenticate user and obtain JWT token"
)
async def login(request: Request):
    """
    Log in with email and password to receive a signed JWT Bearer access token.
    Accepts application/json (with email or username) and application/x-www-form-urlencoded credentials.
    """
    content_type = request.headers.get("content-type", "").lower()
    email_val = None
    username_val = None
    password_val = None

    if "application/x-www-form-urlencoded" in content_type or "multipart/form-data" in content_type:
        try:
            form = await request.form()
            email_val = form.get("email")
            username_val = form.get("username")
            password_val = form.get("password")
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Unable to parse form data: {exc}"
            )
    else:
        try:
            body = await request.json()
            if isinstance(body, dict):
                email_val = body.get("email")
                username_val = body.get("username")
                password_val = body.get("password")
            else:
                raise ValueError("JSON body must be an object")
        except Exception:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Invalid request body. Expected JSON object or form data."
            )

    resolved_email = email_val or username_val
    if not resolved_email or not password_val:
        missing = []
        if not resolved_email:
            missing.append("email/username")
        if not password_val:
            missing.append("password")
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Missing required login field(s): {', '.join(missing)}."
        )

    login_req = UserLoginRequest(
        email=str(resolved_email).strip(),
        username=str(username_val).strip() if username_val else None,
        password=str(password_val),
    )
    return AuthService.authenticate_user(login_req)


@router.get(
    "/me",
    response_model=UserResponse,
    summary="Get current authenticated user profile"
)
async def get_current_user_profile(
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """
    Retrieve profile details of the currently authenticated user based on the provided JWT token.
    """
    return current_user


@router.get(
    "/dashboard-access",
    summary="Validate authoritative role-based dashboard assignment"
)
async def get_role_dashboard_access(
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """
    Returns the single authoritative dashboard and permitted workspace for the authenticated user's role.
    """
    role = current_user.get("role", "Consumer")

    role_dashboard_map = {
        "Consumer": "dashboard.html",
        "Retailer": "retailer-dashboard.html",
        "Food Quality Inspector": "dashboard-inspector.html",
        "Quality Inspector": "dashboard-inspector.html",
        "Warehouse Operator": "warehouse-dashboard.html",
        "Warehouse Manager": "warehouse-dashboard.html",
        "Supply Chain Operator": "warehouse-dashboard.html",
        "Admin": "admin-dashboard.html",
    }

    assigned = role_dashboard_map.get(role, "dashboard.html")

    return {
        "user_id": str(current_user["_id"]),
        "role": role,
        "assigned_dashboard": assigned,
        "allowed_dashboards": [assigned],
    }


@router.post(
    "/logout",
    summary="Invalidate user session and record audit event"
)
async def logout(
    current_user: Optional[Dict[str, Any]] = Depends(get_current_user_optional)
):
    """
    Log out user. If authenticated, records audit log of the logout event.
    """
    if current_user:
        AuditService.log_event(
            action="USER_LOGOUT",
            actor_id=str(current_user.get("_id", "")),
            actor_email=current_user.get("email"),
            actor_role=current_user.get("role"),
            target_resource="users",
            status="success",
        )
    return {"success": True, "message": "Successfully logged out."}


