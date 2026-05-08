from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.config import get_settings
from app.core.security import create_access_token, verify_secret
from app.db.session import get_db
from app.models.web_user import WebUser
from app.schemas.auth import CurrentUserResponse, LoginRequest, LoginResponse

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
    return LoginResponse(username=user.username, role=user.role)


@router.post("/logout")
def logout(response: Response) -> dict[str, str]:
    response.delete_cookie(key="web_admin_token", path="/")
    return {"message": "ok"}


@router.get("/me", response_model=CurrentUserResponse)
def current_user(user: WebUser = Depends(get_current_user)) -> CurrentUserResponse:
    return CurrentUserResponse(username=user.username, role=user.role)
