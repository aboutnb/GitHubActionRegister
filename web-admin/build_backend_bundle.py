from __future__ import annotations

import argparse
import shutil
from pathlib import Path

from PyInstaller.__main__ import run as pyinstaller_run


ROOT = Path(__file__).resolve().parent
BACKEND = ROOT / "backend"
BUILD_ROOT = ROOT / "build"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build PyInstaller backend bundle")
    parser.add_argument("--target-os", required=True, choices=["linux"])
    parser.add_argument("--target-arch", required=True, choices=["amd64", "arm64"])
    return parser.parse_args()


def build_bundle(target_os: str, target_arch: str) -> None:
    dist_root = BUILD_ROOT / "pyinstaller-dist" / f"{target_os}-{target_arch}"
    work_root = BUILD_ROOT / "pyinstaller-work" / f"{target_os}-{target_arch}"
    spec_root = BUILD_ROOT / "pyinstaller-spec" / f"{target_os}-{target_arch}"
    runtime_root = dist_root / "runtime"

    shutil.rmtree(dist_root, ignore_errors=True)
    shutil.rmtree(work_root, ignore_errors=True)
    shutil.rmtree(spec_root, ignore_errors=True)

    pyinstaller_run(
        [
            "--noconfirm",
            "--clean",
            "--onedir",
            "--name",
            "web-admin-backend",
            "--distpath",
            str(runtime_root),
            "--workpath",
            str(work_root),
            "--specpath",
            str(spec_root),
            "--collect-submodules",
            "app",
            "--collect-all",
            "uvicorn",
            "--collect-all",
            "fastapi",
            "--collect-all",
            "starlette",
            "--collect-all",
            "sqlalchemy",
            "--collect-all",
            "psycopg",
            "--collect-all",
            "pydantic",
            "--collect-all",
            "pydantic_settings",
            "--add-data",
            f"{BACKEND / 'sql'}:sql",
            str(BACKEND / "backend_cli.py"),
        ]
    )


def main() -> None:
    args = parse_args()
    build_bundle(args.target_os, args.target_arch)


if __name__ == "__main__":
    main()
