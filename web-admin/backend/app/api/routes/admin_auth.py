from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.config import DEFAULT_ADMIN_PASSWORD, get_settings
from app.core.security import create_access_token, hash_secret, verify_secret
from app.db.session import get_db
from app.models.web_user import WebUser
from app.schemas.auth import ChangePasswordRequest, CurrentUserResponse, LoginRequest, LoginResponse

router = APIRouter(prefix="/admin/auth", tags=["admin-auth"])
settings = get_settings()


@router.post("/login", response_model=LoginResponse)
def login(
    payload: LoginRequest,
    response: Response,
    db: Session = Depends(get_db),
) -> LoginResponse:
    user = db.query(WebUser).filter(WebUser.username == payload.username).first()
    if not user or user.status != "active" or not verify_secret(payload.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    user.last_login_at = datetime.now(timezone.utc)
    db.commit()
    token = create_access_token(user.username, {"role": user.role})
    response.set_cookie(
        key="web_admin_token",
        value=token,
        httponly=True,
        samesite="lax",
        secure=settings.cookie_secure,
        max_age=60 * 60 * 12,
        path="/",
    )
    return LoginResponse(
        username=user.username,
        role=user.role,
        must_change_password=user.must_change_password,
    )


@router.post("/logout")
def logout(response: Response) -> dict[str, str]:
    response.delete_cookie(key="web_admin_token", path="/")
    return {"message": "ok"}


@router.get("/me", response_model=CurrentUserResponse)
def current_user(user: WebUser = Depends(get_current_user)) -> CurrentUserResponse:
    return CurrentUserResponse(
        username=user.username,
        role=user.role,
        must_change_password=user.must_change_password,
    )


@router.post("/change-password")
def change_password(
    payload: ChangePasswordRequest,
    user: WebUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, bool]:
    if not verify_secret(payload.current_password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Current password is incorrect")
    if payload.new_password == DEFAULT_ADMIN_PASSWORD:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="New password cannot use default password")
    if len(payload.new_password) < 8:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="New password must be at least 8 characters")

    user.password_hash = hash_secret(payload.new_password)
    user.must_change_password = False
    db.commit()
    return {"ok": True}
