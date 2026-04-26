# GitHubRegister

`GitHubRegister` 是一个基于 `Python + PySide6 + Playwright + BitBrowser` 的桌面自动化工具，主要用于批量执行 GitHub 账号注册相关流程。

## 项目能力

- 导入邮箱账号列表，批量发起注册
- 通过 BitBrowser 打开独立浏览器环境
- 自动填写 GitHub 注册表单
- 在人工处理验证码后继续执行后续流程
- 自动读取邮箱验证码并提交
- 自动尝试开启 2FA 并导出恢复码
- 记录成功、失败和失败账号清单

## 主要模块

- `main.py`：程序入口与任务调度
- `ui_qt.py`：桌面图形界面
- `github_automation.py`：GitHub 注册自动化流程
- `bitbrower.py`：BitBrowser API 封装
- `proxy_config.py`：代理与 BitBrowser 配置管理
- `xiaoshuidi_mail.py`：邮箱验证码获取逻辑

## 运行依赖

- Python 3
- PySide6
- Playwright
- BitBrowser 本地服务
- 可用代理配置

## 打包方式

本项目当前提供两套打包配置：

- macOS：`GitHubRegister.spec`
- Windows：`GitHubRegister-win.spec`

统一入口脚本：

```bash
python package_app.py
```

`package_app.py` 会根据当前系统自动选择对应的 `.spec` 文件。

## macOS 打包

### 1. 环境准备

```bash
pip install -r requirements.txt
pip install pyinstaller
playwright install chromium
```

### 2. 执行打包

```bash
python package_app.py
```

### 3. 打包产物

```text
dist/GitHubRegister.app
```

### 4. 如果 macOS 提示“应用已损坏”

```bash
xattr -cr dist/GitHubRegister.app
```

## Windows 打包

不能在 macOS 直接打出可运行的 Windows `.exe`，必须在 Windows 环境执行。

### 1. 环境准备

```bat
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
pip install pyinstaller
playwright install chromium
```

### 2. 执行打包

```bat
python package_app.py
```

### 3. 打包产物

```text
dist\GitHubRegister\GitHubRegister.exe
```

## 图标资源

图标生成脚本：

```bash
python assets/generate_icon.py
```

会同时生成：

- `assets/icon.png`：用于 macOS
- `assets/icon.ico`：用于 Windows

如果修改了图标，需要重新执行打包，新的图标才会进入应用包。

## 常见问题

### 1. `No module named PyInstaller`

说明当前 Python 环境没有安装 `PyInstaller`：

```bash
python -m pip install pyinstaller
```

### 2. `playwright` 相关资源缺失

重新安装浏览器：

```bash
playwright install chromium
```

### 3. Windows 打包后双击无反应

优先检查：

- 是否在 Windows 本机打包
- 是否完整安装 `requirements.txt`
- 是否执行过 `playwright install chromium`

### 4. macOS 图标或应用未刷新

先完全退出旧应用，再打开新包。必要时重新打包。
