from __future__ import annotations

from functools import lru_cache
from pathlib import Path
import re
from urllib.parse import urlparse
from typing import List

from pydantic import Field
from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import URL

from app.runtime import backend_dir, env_file


BACKEND_DIR = backend_dir()
ENV_FILE = env_file()


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(ENV_FILE),
        env_prefix="WEB_ADMIN_",
        extra="ignore",
    )

    app_name: str = "GitHub Asset Center"
    api_prefix: str = "/api"
    host: str = "0.0.0.0"
    port: int = 18700
    workers: int = 1
    log_level: str = "info"
    serve_frontend: bool = True
    frontend_dist: str = "../frontend/dist"
    database_url: str | None = None
    database_admin_url: str | None = None
    database_scheme: str = "postgresql+psycopg"
    database_host: str = "127.0.0.1"
    database_port: int = 5432
    database_name: str = "github_asset_center"
    database_user: str = "postgres"
    database_password: str = "123456"
    database_admin_database: str = "postgres"
    database_bootstrap: bool = True
    jwt_secret: str = "change-me"
    jwt_expire_minutes: int = 720
    encrypt_secret: str = "change-me-too"
    app_env: str = "development"
    admin_username: str = "admin"
    admin_password: str = ""
    mail_lease_minutes: int = 30
    cors_origins: List[str] = Field(
        default_factory=lambda: ["http://127.0.0.1:18701", "http://localhost:18701"]
    )
    cors_origin_regex: str | None = None
    cookie_secure: bool = False
    docs_enabled: bool = True

    @staticmethod
    def _build_postgres_url(
        scheme: str,
        username: str,
        password: str,
        host: str,
        port: int,
        database: str,
    ) -> str:
        return URL.create(
            scheme,
            username=username,
            password=password,
            host=host,
            port=port,
            database=database,
        ).render_as_string(hide_password=False)

    @property
    def frontend_dist_path(self) -> Path:
        path = Path(self.frontend_dist)
        if path.is_absolute():
            return path
        return (BACKEND_DIR / path).resolve()

    @model_validator(mode="after")
    def validate_security(self):
        if not self.database_url:
            if not self.database_scheme.startswith("postgresql"):
                raise ValueError("未设置 WEB_ADMIN_DATABASE_URL 时，仅支持自动拼装 PostgreSQL 连接")
            self.database_url = self._build_postgres_url(
                scheme=self.database_scheme,
                username=self.database_user,
                password=self.database_password,
                host=self.database_host,
                port=self.database_port,
                database=self.database_name,
            )
        if not self.database_admin_url and self.database_url:
            parsed = urlparse(self.database_url)
            if parsed.scheme.startswith("postgresql") and parsed.hostname:
                self.database_admin_url = self._build_postgres_url(
                    scheme=parsed.scheme,
                    username=parsed.username or self.database_user,
                    password=parsed.password or self.database_password,
                    host=parsed.hostname,
                    port=parsed.port or self.database_port,
                    database=self.database_admin_database,
                )
        if self.jwt_secret in {"change-me", "quantify-web-admin-secret"}:
            raise ValueError("WEB_ADMIN_JWT_SECRET 不能使用默认值")
        if self.encrypt_secret in {"change-me-too", "quantify-web-admin-secret-too"}:
            raise ValueError("WEB_ADMIN_ENCRYPT_SECRET 不能使用默认值")
        if self.app_env == "production" and self.docs_enabled:
            raise ValueError("生产环境必须关闭 docs/openapi")
        if self.app_env == "development" and not self.cors_origin_regex:
            self.cors_origin_regex = r"^https?://(127\.0\.0\.1|localhost)(:\d+)?$"
        if self.cors_origin_regex:
            re.compile(self.cors_origin_regex)
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
