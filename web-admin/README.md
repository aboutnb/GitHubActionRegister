# Web Admin

这是一个面向 Linux 服务器的 `web-admin` 部署包，不包含桌面端。本地如果使用 Docker Desktop，也可以在 macOS 上先跑安装脚本做验收。

现在改为 Docker 发布：

- GitHub Actions 构建并推送多架构镜像
- 支持 `linux/amd64` 和 `linux/arm64`
- 服务器只需要 Docker 和 Docker Compose
- 不再依赖 PyInstaller、本机 Python、glibc 版本

镜像地址：

- `ghcr.io/aboutnb/github-action-web-admin:latest`
- `ghcr.io/aboutnb/github-action-web-admin:web-admin-vX.Y.Z`

## 生产安装

服务器执行：

```bash
curl -fsSL https://github.com/aboutnb/GitHubAction/releases/latest/download/install-web-admin.sh | bash
```

如果希望真正一条命令完成首次部署，直接把配置作为安装脚本参数传进去：

```bash
curl -fsSL https://github.com/aboutnb/GitHubAction/releases/latest/download/install-web-admin.sh | bash -s -- \
  --database-url 'postgresql+psycopg://postgres:123456@127.0.0.1:5432/github_asset_center' \
  --jwt-secret 'replace-with-a-long-random-secret' \
  --encrypt-secret 'replace-with-a-different-long-random-secret' \
  --admin-password 'replace-with-a-strong-password'
```

安装脚本会：

- 创建 `/opt/web-admin/backend/.env`
- 创建 `/opt/web-admin/docker-compose.yml`
- 拉取最新 Docker 镜像
- 使用 Docker Compose 启动容器
- 等待健康检查通过后输出访问地址

## 首次配置

第一次执行时，如果没有 `.env`，安装脚本会：

- 如果你已经通过安装脚本参数传入核心配置，则直接写入 `.env` 并继续部署
- 否则生成模板并退出，等你编辑后再次执行

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

配置完后再次执行：

```bash
curl -fsSL https://github.com/aboutnb/GitHubAction/releases/latest/download/install-web-admin.sh | bash
```

如果数据库已经提前建好，推荐首次就带上：

```bash
curl -fsSL https://github.com/aboutnb/GitHubAction/releases/latest/download/install-web-admin.sh | bash -s -- \
  --database-url 'postgresql+psycopg://postgres:123456@127.0.0.1:5432/github_asset_center' \
  --jwt-secret 'replace-with-a-long-random-secret' \
  --encrypt-secret 'replace-with-a-different-long-random-secret' \
  --admin-password 'replace-with-a-strong-password' \
  --database-bootstrap false
```

## 容器管理

查看容器：

```bash
docker ps
docker logs -f web-admin
```

重启：

```bash
docker restart web-admin
```

停止：

```bash
docker stop web-admin
```

## 发布方式

推送 tag：

```bash
git tag web-admin-v1.0.0
git push origin web-admin-v1.0.0
```

GitHub Actions 会构建并推送：

- `ghcr.io/aboutnb/github-action-web-admin:latest`
- `ghcr.io/aboutnb/github-action-web-admin:web-admin-v1.0.0`
- `install-web-admin.sh` Release 资产

## 访问

- `http://<server-ip>:18700`
