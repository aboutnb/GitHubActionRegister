from app.core.config import get_settings
from app.bootstrap import seed_admin_user
from app.db.session import SessionLocal


def main() -> None:
    settings = get_settings()
    if not settings.admin_password:
        raise SystemExit("WEB_ADMIN_ADMIN_PASSWORD 未设置，拒绝创建管理员账号")
    db = SessionLocal()
    try:
        user = seed_admin_user(
            db,
            username=settings.admin_username,
            password=settings.admin_password,
        )
        print(f"created or reused admin user: {user.username}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
