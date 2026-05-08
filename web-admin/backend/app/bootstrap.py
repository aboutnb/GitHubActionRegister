from sqlalchemy.orm import Session

from app.core.security import hash_secret
from app.models.web_user import WebUser


def seed_admin_user(db: Session, username: str, password: str, role: str = "admin") -> WebUser:
    existing = db.query(WebUser).filter(WebUser.username == username).first()
    if existing:
        return existing

    user = WebUser(
        username=username,
        password_hash=hash_secret(password),
        role=role,
        status="active",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user
