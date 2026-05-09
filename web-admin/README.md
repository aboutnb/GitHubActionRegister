# Web Admin

这是一个可直接用于生产部署的 `web-admin` Linux 发布包，不包含桌面端。
后端使用 PyInstaller 打包，Release 中不再直接包含后端 Python 源码。
为兼容较老的 Linux 发行版，后端二进制会在 `manylinux2014` 基线环境中构建，并使用带共享库的独立 Python 运行时来完成 PyInstaller 打包。

## 生产安装

服务器执行：

```bash
curl -fsSL https://github.com/OWNER/REPO/releases/latest/download/install-web-admin.sh | bash
```

安装脚本会：

- 自动识别服务器是 `amd64` 还是 `arm64`
- 下载对应的 `web-admin-linux-<arch>.tar.gz`
- 解压到 `/opt/web-admin`
- 保留 `backend/.env`
- 执行初始化
- 注册 `systemd` 服务
- 启动 `web-admin`

当前正式支持的发布产物：

- Linux AMD64
- Linux ARM64

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
- `WEB_ADMIN_JWT_SECRET`
- `WEB_ADMIN_ENCRYPT_SECRET`
- `WEB_ADMIN_ADMIN_PASSWORD`

常见可选项：

- `WEB_ADMIN_DATABASE_BOOTSTRAP=false`
  - 数据库已经存在，或者当前数据库用户没有建库权限时使用
- `WEB_ADMIN_DATABASE_ADMIN_URL`
  - 需要单独提供高权限连接来自动建库时使用
- `WEB_ADMIN_PORT`
  - 需要修改服务端口时使用

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

- `web-admin-linux-amd64.tar.gz`
- `web-admin-linux-arm64.tar.gz`
- `install-web-admin.sh`

## 访问

- `http://<server-ip>:18700`
