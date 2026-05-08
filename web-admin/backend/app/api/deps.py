from __future__ import annotations

from fastapi import Cookie, Depends, Header, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.core.security import decode_access_token, verify_secret
from app.db.session import get_db
from app.models.desktop_client import DesktopClient
from app.models.web_user import WebUser

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/admin/auth/login", auto_error=False)


def get_current_user(
    bearer_token: str | None = Depends(oauth2_scheme),
    cookie_token: str | None = Cookie(default=None, alias="web_admin_token"),
    db: Session = Depends(get_db),
) -> WebUser:
    credentials_error = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid access token",
    )
    try:
        payload = decode_access_token(cookie_token or bearer_token or "")
    except Exception as exc:  # pragma: no cover - auth boundary
        raise credentials_error from exc

    username = payload.get("sub")
    if not username:
        raise credentials_error

    user = db.query(WebUser).filter(WebUser.username == username, WebUser.status == "active").first()
    if not user:
        raise credentials_error
    return user


def get_current_client(
    x_api_token: str = Header(..., alias="X-Api-Token"),
    db: Session = Depends(get_db),
) -> DesktopClient:
    clients = db.query(DesktopClient).filter(DesktopClient.status == "active").all()
    for client in clients:
        if verify_secret(x_api_token, client.token_hash):
            return client
    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid client token")
