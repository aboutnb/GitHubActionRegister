# Web Admin

后台管理前后端一体部署，适合上传到 GitHub 后在服务器终端直接执行一键部署。

## 部署方式

首次部署：

```bash
git clone <your-repo-url>
cd GitHubAction/web-admin
cp backend/.env.example backend/.env
vim backend/.env
./deploy.sh
```

后续更新并部署：

```bash
cd GitHubAction/web-admin
./deploy.sh --pull
```

## 脚本会做什么

`deploy.sh` 会调用 `deploy.py`，自动完成：

- 前端依赖安装
- 前端构建
- 后端虚拟环境创建
- 后端依赖安装
- 按配置建库
- 初始化表结构
- 初始化管理员账号
- 启动 FastAPI 服务

## 依赖

- Python 3.11+
- Node.js 18+
- PostgreSQL

## 必配项

复制 `backend/.env.example` 到 `backend/.env` 后，至少修改这些配置：

- `WEB_ADMIN_DATABASE_URL`
- `WEB_ADMIN_DATABASE_ADMIN_URL`
- `WEB_ADMIN_JWT_SECRET`
- `WEB_ADMIN_ENCRYPT_SECRET`
- `WEB_ADMIN_ADMIN_PASSWORD`

可选启动配置：

- `WEB_ADMIN_HOST`
- `WEB_ADMIN_PORT`
- `WEB_ADMIN_WORKERS`
- `WEB_ADMIN_LOG_LEVEL`

## 访问

- 后台地址：`http://<server-ip>:18700`
- API：`http://<server-ip>:18700/api`

## 说明

- 前端构建产物由后端直接托管，不需要单独起前端服务
- 数据库连接和建库连接都支持通过环境变量配置
- 默认是 HTTP 可直接登录，若前面挂了 HTTPS 反代，再把 `WEB_ADMIN_COOKIE_SECURE=true`
- 建议后续再配 `systemd` 或 `supervisor` 托管进程
