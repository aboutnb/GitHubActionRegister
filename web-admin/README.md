# Web Admin

只包含后台管理的前后端部署包。

## GitHub Releases 安装

发布新版本后，服务器可直接执行：

```bash
curl -fsSL https://github.com/OWNER/REPO/releases/latest/download/install-web-admin.sh | bash
```

安装完成后，访问：

- `http://<server-ip>:18700`

## Release 内容

GitHub Release 里只打包 `web-admin/`，不包含桌面端代码。

## 服务器部署流程

1. 打 tag，例如 `web-admin-v1.0.0`
2. GitHub Actions 自动生成 `web-admin.tar.gz`
3. 服务器下载 Release 附件
4. 解压到目标目录
5. 执行 `deploy.sh`

## 配置

先复制：

```bash
cp backend/.env.example backend/.env
```

至少修改：

- `WEB_ADMIN_DATABASE_URL`
- `WEB_ADMIN_DATABASE_ADMIN_URL`
- `WEB_ADMIN_JWT_SECRET`
- `WEB_ADMIN_ENCRYPT_SECRET`
- `WEB_ADMIN_ADMIN_PASSWORD`

## 说明

- 前端已内置到后端静态发布
- Release 包不带 `backend/.env`
- Release 包不带 `backend/.venv`
- Release 包不带 `frontend/node_modules`
