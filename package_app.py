import shutil
import subprocess
import sys
import importlib.util
from pathlib import Path


APP_NAME = "GitHubRegister"
BUNDLE_ID = "com.xiaobo.githubregister"
PROJECT_ROOT = Path(__file__).resolve().parent
BUILD_DIRS = ("build", "dist", f"{APP_NAME}.build", f"{APP_NAME}.dist", f"{APP_NAME}.app")


def clean_old_builds() -> None:
    """清理 Nuitka 和历史 PyInstaller 产物，避免旧文件混入。"""
    print(">>> 正在清理旧的编译文件...")
    for name in BUILD_DIRS:
        path = PROJECT_ROOT / name
        if path.is_dir():
            shutil.rmtree(path)
            print(f"    已删除 {path.name}/")
        elif path.exists():
            path.unlink()
            print(f"    已删除 {path.name}")


def ensure_nuitka_installed() -> None:
    required_modules = ("nuitka", "ordered_set", "zstandard")
    missing = [name for name in required_modules if importlib.util.find_spec(name) is None]
    if not missing:
        return

    print("\n>>> 错误：当前 Python 环境缺少 Nuitka 打包依赖")
    print(f">>> 当前解释器: {sys.executable}")
    print(f">>> 缺少模块: {', '.join(missing)}")
    print(">>> 请先安装：")
    print(f"    {sys.executable} -m pip install Nuitka ordered-set zstandard")
    sys.exit(1)


def build_command() -> list[str]:
    cmd = [
        sys.executable,
        "-m",
        "nuitka",
        "--assume-yes-for-downloads",
        "--deployment",
        "--output-dir=dist",
        f"--output-folder-name={APP_NAME}",
        f"--output-filename={APP_NAME}",
        "--enable-plugins=pyside6",
        "--include-data-dir=assets=assets",
        "--python-flag=no_site",
    ]

    if sys.platform == "darwin":
        cmd.extend(
            [
                "--mode=app-dist",
                "--macos-app-name=GitHubRegister",
                f"--macos-signed-app-name={BUNDLE_ID}",
                "--macos-app-mode=gui",
                "--macos-app-icon=assets/icon.icns",
            ]
        )
    elif sys.platform == "win32":
        cmd.extend(
            [
                "--mode=standalone",
                "--windows-console-mode=disable",
                "--windows-icon-from-ico=assets/icon.ico",
            ]
        )
    else:
        cmd.extend(
            [
                "--mode=standalone",
            ]
        )

    cmd.append("main.py")
    return cmd


def print_success_hint() -> None:
    print("\n" + "=" * 60)
    print(">>> 打包成功！")
    if sys.platform == "darwin":
        app_path = PROJECT_ROOT / "dist" / f"{APP_NAME}.app"
        print(f">>> 应用位于: {app_path}")
        print("\n>>> macOS 提示：如果首次打开提示“应用已损坏”或被阻止，请运行：")
        print(f"    xattr -cr {app_path}")
    elif sys.platform == "win32":
        exe_path = PROJECT_ROOT / "dist" / f"{APP_NAME}.dist" / f"{APP_NAME}.exe"
        print(f">>> Windows 产物: {exe_path}")
    else:
        binary_path = PROJECT_ROOT / "dist" / f"{APP_NAME}.dist" / APP_NAME
        print(f">>> Linux 产物: {binary_path}")
    print("=" * 60)


def run_packaging() -> None:
    clean_old_builds()
    ensure_nuitka_installed()
    cmd = build_command()

    print("\n" + "=" * 60)
    print(f">>> 开始自动打包: {APP_NAME}")
    print(">>> 执行命令:", " ".join(cmd))
    print("=" * 60 + "\n")

    try:
        subprocess.check_call(cmd, cwd=PROJECT_ROOT)
        print_success_hint()
    except subprocess.CalledProcessError as exc:
        print(f"\n>>> 打包失败: {exc}")
        sys.exit(exc.returncode)
    except FileNotFoundError:
        print("\n>>> 错误：未找到 Nuitka，请先执行:")
        print(f"    {sys.executable} -m pip install Nuitka ordered-set zstandard")
        sys.exit(1)


if __name__ == "__main__":
    run_packaging()
