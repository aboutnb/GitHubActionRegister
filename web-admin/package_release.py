from __future__ import annotations

import argparse
import shutil
import tarfile
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parent
BUILD_ROOT = ROOT / "build"
BACKEND = ROOT / "backend"
FRONTEND = ROOT / "frontend"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Package release assets for web-admin")
    parser.add_argument("--target-os", required=True, choices=["linux"])
    parser.add_argument("--target-arch", required=True, choices=["amd64", "arm64"])
    return parser.parse_args()


def copy_tree(src: Path, dst: Path) -> None:
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src, dst)


def build_release_tree(target_os: str, target_arch: str) -> tuple[Path, Path]:
    package_root = BUILD_ROOT / "package" / f"{target_os}-{target_arch}"
    release_root = package_root / "web-admin"
    runtime_src = BUILD_ROOT / "pyinstaller-dist" / f"{target_os}-{target_arch}" / "runtime" / "web-admin-backend"
    runtime_dst = release_root / "backend" / "runtime"

    shutil.rmtree(package_root, ignore_errors=True)
    (release_root / "backend").mkdir(parents=True, exist_ok=True)
    (release_root / "frontend").mkdir(parents=True, exist_ok=True)

    shutil.copy2(BACKEND / ".env.example", release_root / "backend" / ".env.example")
    shutil.copy2(ROOT / "web-admin.service", release_root / "web-admin.service")
    shutil.copy2(ROOT / "README.md", release_root / "README.md")
    copy_tree(runtime_src, runtime_dst)
    copy_tree(FRONTEND / "dist", release_root / "frontend" / "dist")
    return package_root, release_root


def archive_release(package_root: Path, target_os: str, target_arch: str) -> Path:
    dist_root = BUILD_ROOT / "artifacts"
    dist_root.mkdir(parents=True, exist_ok=True)
    archive_path = dist_root / f"web-admin-{target_os}-{target_arch}.tar.gz"
    with tarfile.open(archive_path, "w:gz") as tar:
        tar.add(package_root / "web-admin", arcname="web-admin")
    return archive_path


def main() -> None:
    args = parse_args()
    package_root, _ = build_release_tree(args.target_os, args.target_arch)
    archive_path = archive_release(package_root, args.target_os, args.target_arch)
    print(archive_path)


if __name__ == "__main__":
    main()
