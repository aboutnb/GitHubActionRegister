from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent
BACKEND = ROOT / "backend"
FRONTEND = ROOT / "frontend"


def run(cmd: list[str], cwd: Path | None = None, env: dict[str, str] | None = None) -> None:
    print(f"$ {' '.join(cmd)}")
    subprocess.run(cmd, cwd=cwd, env=env, check=True)


def backend_python() -> str:
    venv_python = BACKEND / ".venv" / "bin" / "python"
    if not venv_python.exists():
        run([sys.executable, "-m", "venv", ".venv"], cwd=BACKEND)
    run([str(venv_python), "-m", "pip", "install", "-r", "requirements.txt"], cwd=BACKEND)
    return str(venv_python)


def ensure_frontend_built() -> None:
    if os.environ.get("WEB_ADMIN_SKIP_FRONTEND_BUILD") == "true":
        if not (FRONTEND / "dist" / "index.html").exists():
            raise SystemExit("已设置跳过前端构建，但 frontend/dist 不存在")
        return
    if not (FRONTEND / "node_modules").exists():
        run(["npm", "install"], cwd=FRONTEND)
    run(["npm", "run", "build"], cwd=FRONTEND)


def prepare_env() -> dict[str, str]:
    env = os.environ.copy()
    env.setdefault("WEB_ADMIN_SERVE_FRONTEND", "true")
    env.setdefault("WEB_ADMIN_APP_ENV", "production")
    env.setdefault("WEB_ADMIN_DOCS_ENABLED", "false")
    env.setdefault("WEB_ADMIN_COOKIE_SECURE", "false")
    return env


def prepare_runtime(env: dict[str, str]) -> None:
    os.chdir(ROOT)
    py = backend_python()
    ensure_frontend_built()
    run([py, "create_database.py"], cwd=BACKEND, env=env)
    run([py, "init_db.py"], cwd=BACKEND, env=env)
    run([py, "create_admin.py"], cwd=BACKEND, env=env)


def serve_runtime(env: dict[str, str]) -> None:
    py = str(BACKEND / ".venv" / "bin" / "python")
    if not Path(py).exists():
        raise SystemExit("backend/.venv 不存在，请先执行 prepare")
    host = env.get("WEB_ADMIN_HOST", "0.0.0.0")
    port = env.get("WEB_ADMIN_PORT", "18700")
    workers = env.get("WEB_ADMIN_WORKERS", "1")
    log_level = env.get("WEB_ADMIN_LOG_LEVEL", "info")
    run(
        [
            py,
            "-m",
            "uvicorn",
            "app.main:app",
            "--host",
            host,
            "--port",
            port,
            "--workers",
            workers,
            "--log-level",
            log_level,
        ],
        cwd=BACKEND,
        env=env,
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Deploy web admin")
    parser.add_argument(
        "command",
        nargs="?",
        default="deploy",
        choices=["deploy", "prepare", "serve"],
        help="deploy=prepare+serve, prepare=install/init only, serve=start uvicorn only",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    env = prepare_env()
    if args.command in {"deploy", "prepare"}:
        prepare_runtime(env)
    if args.command in {"deploy", "serve"}:
        serve_runtime(env)


if __name__ == "__main__":
    main()
