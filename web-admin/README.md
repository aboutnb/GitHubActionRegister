# Web Admin

这是一个可直接用于生产部署的 `web-admin` 发布包，不包含桌面端。

## 生产安装

服务器执行：

```bash
curl -fsSL https://github.com/OWNER/REPO/releases/latest/download/install-web-admin.sh | bash
```

安装脚本会：

- 下载最新 `web-admin.tar.gz`
- 解压到 `/opt/web-admin`
- 保留 `backend/.env`
- 保留 `backend/.venv`
- 执行初始化
- 注册 `systemd` 服务
- 启动 `web-admin`

## 服务管理

```bash
sudo systemctl status web-admin
sudo systemctl restart web-admin
sudo systemctl stop web-admin
sudo journalctl -u web-admin -f
```

## 首次配置

第一次执行时，如果没有 `.env`，安装脚本会先生成模板并退出。

然后编辑：

```bash
sudo vim /opt/web-admin/backend/.env
```

至少设置：

- `WEB_ADMIN_DATABASE_URL`
- `WEB_ADMIN_DATABASE_ADMIN_URL`
- `WEB_ADMIN_JWT_SECRET`
- `WEB_ADMIN_ENCRYPT_SECRET`
- `WEB_ADMIN_ADMIN_PASSWORD`

配置完后执行：

```bash
curl -fsSL https://github.com/OWNER/REPO/releases/latest/download/install-web-admin.sh | bash
```

## 发布方式

推送 tag：

```bash
git tag web-admin-v1.0.0
git push origin web-admin-v1.0.0
```

GitHub Actions 会只打包 `web-admin/`，生成：

- `web-admin.tar.gz`
- `install-web-admin.sh`

## 访问

- `http://<server-ip>:18700`
