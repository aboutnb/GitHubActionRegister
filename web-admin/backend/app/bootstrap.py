from sqlalchemy.orm import Session

from app.core.config import DEFAULT_ADMIN_PASSWORD
from app.core.security import hash_secret, verify_secret
from app.models.web_user import WebUser


def seed_admin_user(db: Session, username: str, password: str, role: str = "admin") -> WebUser:
    existing = db.query(WebUser).filter(WebUser.username == username).first()
    if existing:
        if (
            password == DEFAULT_ADMIN_PASSWORD
            and verify_secret(DEFAULT_ADMIN_PASSWORD, existing.password_hash)
            and not existing.must_change_password
        ):
            existing.must_change_password = True
            db.commit()
            db.refresh(existing)
        return existing

    user = WebUser(
        username=username,
        password_hash=hash_secret(password),
        role=role,
        status="active",
        must_change_password=password == DEFAULT_ADMIN_PASSWORD,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user
