import sys
import os
import shutil
import subprocess
import importlib.util

# ---------------------------------------------------------------------------
# 打包配置
# ---------------------------------------------------------------------------
app_name = "GitHubRegister"
pyinstaller_cache_dir = os.path.abspath(".pyinstaller-cache")


def get_spec_file() -> str:
    if sys.platform == "win32":
        return f"{app_name}-win.spec"
    return f"{app_name}.spec"

def clean_old_builds():
    """ 自动清理旧的编译文件 """
    print(">>> 正在清理旧的编译文件...")
    for folder in ['build', 'dist']:
        if os.path.exists(folder):
            shutil.rmtree(folder)
            print(f"    已删除 {folder}/")

def run_packaging():
    clean_old_builds()
    spec_file = get_spec_file()

    if not os.path.exists(spec_file):
        print(f"\n>>> 错误：未找到打包配置文件 {spec_file}")
        sys.exit(1)
    
    if importlib.util.find_spec("PyInstaller") is None:
        print("\n>>> 错误：当前 Python 环境未安装 PyInstaller")
        print(f">>> 当前解释器: {sys.executable}")
        print(">>> 请先安装：")
        print(f"    {sys.executable} -m pip install pyinstaller")
        sys.exit(1)

    # 统一使用仓库内的 .spec，避免命令行参数和 spec 配置漂移。
    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        spec_file,
    ]
    
    print("\n" + "=" * 60)
    print(f">>> 开始自动打包: {app_name}")
    print(">>> 执行命令:", " ".join(cmd))
    print("=" * 60 + "\n")
    
    try:
        env = os.environ.copy()
        env["PYINSTALLER_CONFIG_DIR"] = pyinstaller_cache_dir
        os.makedirs(pyinstaller_cache_dir, exist_ok=True)
        subprocess.check_call(cmd, env=env)
        
        print("\n" + "=" * 60)
        print(">>> 打包成功！")
        print(f">>> 可执行文件位于: {os.path.abspath('dist')}")
        
        if sys.platform == "darwin":
            app_path = os.path.join("dist", f"{app_name}.app")
            print(f"\n>>> macOS 提示：如果启动报错“应用损坏”，请运行：")
            print(f"    xattr -cr {app_path}")
        elif sys.platform == "win32":
            exe_path = os.path.join("dist", app_name, f"{app_name}.exe")
            print(f"\n>>> Windows 产物：")
            print(f"    {os.path.abspath(exe_path)}")
        
        print("=" * 60)
        
    except subprocess.CalledProcessError as e:
        print(f"\n>>> 打包失败: {e}")
    except FileNotFoundError:
        print("\n>>> 错误：未找到 pyinstaller，请先执行: pip install pyinstaller")

if __name__ == "__main__":
    run_packaging()
