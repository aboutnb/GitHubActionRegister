from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api.routes import (
    admin_auth,
    admin_batches,
    admin_clients,
    admin_dashboard,
    admin_github_accounts,
    admin_logs,
    admin_mail_accounts,
    client_sync,
)
from app.core.config import get_settings

settings = get_settings()
frontend_dist = settings.frontend_dist_path

app = FastAPI(
    title=settings.app_name,
    docs_url="/docs" if settings.docs_enabled else None,
    redoc_url="/redoc" if settings.docs_enabled else None,
    openapi_url="/openapi.json" if settings.docs_enabled else None,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_origin_regex=settings.cors_origin_regex,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(admin_auth.router, prefix=settings.api_prefix)
app.include_router(admin_dashboard.router, prefix=settings.api_prefix)
app.include_router(admin_mail_accounts.router, prefix=settings.api_prefix)
app.include_router(admin_github_accounts.router, prefix=settings.api_prefix)
app.include_router(admin_clients.router, prefix=settings.api_prefix)
app.include_router(admin_batches.router, prefix=settings.api_prefix)
app.include_router(admin_logs.router, prefix=settings.api_prefix)
app.include_router(client_sync.router, prefix=settings.api_prefix)

if settings.serve_frontend and frontend_dist.exists():
    assets_dir = frontend_dist / "assets"
    if assets_dir.exists():
        app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/{full_path:path}", include_in_schema=False)
def serve_frontend(full_path: str):
    if full_path.startswith("api") or full_path.startswith("docs") or full_path.startswith("redoc"):
        raise HTTPException(status_code=404, detail="Not Found")

    if not settings.serve_frontend or not frontend_dist.exists():
        raise HTTPException(status_code=404, detail="Frontend not built")

    file_path = frontend_dist / Path(full_path)
    if full_path and file_path.is_file():
        return FileResponse(file_path)

    index_file = frontend_dist / "index.html"
    if index_file.exists():
        return FileResponse(index_file)
    raise HTTPException(status_code=404, detail="Frontend not built")
