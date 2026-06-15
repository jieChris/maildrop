# Maildrop Codex 部署说明

本文件给 Codex/AI 部署代理读取。所有回复默认使用简体中文。

详细傻瓜自动部署步骤见 `docs/deploy-for-ai.md`。如果本文件和
`docs/deploy-for-ai.md` 都提到同一事项，以更具体、更保守的要求为准。

## 项目目标

Maildrop 是一个自托管轻量收信系统：

- Postfix 接收 catch-all 邮件。
- FastAPI 提供 ingest、公开 inbox API 和中文后台。
- PostgreSQL 保存 alias、邮件、未登记邮件、收件管理器和后台登记子域名。
- Caddy 对外提供 HTTPS，并屏蔽 `/internal/*`。

## AI 可以自动完成的事项

在部署者提供服务器 SSH、域名和服务器 IP 后，可以自动完成：

1. 同步代码到服务器，默认路径 `/opt/maildrop`。
2. 生成或更新 `.env.maildrop`，但不得打印真实密钥。
3. 构建 Docker app 镜像。
4. 启动 PostgreSQL 和 app。
5. 执行 `alembic upgrade head`。
6. 安装 Postfix pipe 脚本 `/usr/local/bin/mail-api-ingest`。
7. 写入 `/etc/mail-api-ingest.env`，权限为 `root:mailapi 0640`。
8. 用 `postconf -e` 和 `postconf -M -e` 幂等配置 Postfix。
9. 安装 `/etc/postfix/virtual_mailbox_domains_regexp` 和 `/etc/postfix/virtual_mailbox_regexp`。
10. 配置 Caddy 反代到 `127.0.0.1:8000`，并对 `/internal/*` 返回 404。
11. 运行本地测试、生产健康检查、SMTP smoke。

## AI 必须提醒人工完成的事项

AI 通常不能直接登录部署者的 DNS 服务商后台。部署前必须提醒部署者手动配置 DNS：

- `mail.<domain>` A 到服务器公网 IP。
- `<domain>` MX 到 `mail.<domain>.`，优先级 `10`。
- `<domain>` TXT 为 `v=spf1 -all`。
- `_dmarc.<domain>` TXT 为 `v=DMARC1; p=reject; sp=reject; adkim=s; aspf=s`。
- 如果使用 `*.exa.<domain>`，添加 `*.exa` 和 `exa` 的 MX/TXT。
- 删除 Spaceship Email Forwarding Free 或其他旧 MX，避免 MX 冲突。
- 确认服务器防火墙开放 TCP `25`、`80`、`443`。

Spaceship 操作细节见 `docs/spaceship-dns.md`。

## 部署前必须收集的信息

向部署者确认：

- 域名，例如 `example.com`。
- 服务器公网 IP。
- SSH 主机，例如 `root@203.0.113.10` 或 SSH alias。
- 后台用户名，默认可用 `admin`。
- 是否需要固定子域名，例如 `ssn.example.com`。
- 是否需要登记式 `exa` 通配子域名。
- 是否需要 Spaceship 只读 API 同步 OpenAI TXT 子域名。
- 是否要保留 EmailEngine 历史文件；新部署通常只需要 Maildrop。

## 服务器部署步骤

以下命令中的变量由部署者实际信息替换。

```bash
DOMAIN=example.com
SERVER_IP=203.0.113.10
SSH_HOST=root@203.0.113.10
APP_DIR=/opt/maildrop
```

同步代码：

```bash
ssh "$SSH_HOST" "mkdir -p $APP_DIR"
rsync -az --delete \
  --exclude .git \
  --exclude .venv \
  --exclude .pytest_cache \
  --exclude .env \
  --exclude .env.maildrop \
  --exclude __pycache__ \
  --exclude '*.pyc' \
  ./ "$SSH_HOST:$APP_DIR/"
```

创建 `.env.maildrop`：

```bash
ssh "$SSH_HOST" "cd $APP_DIR && cp .env.maildrop.example .env.maildrop"
```

然后在服务器上用脚本替换：

- `APP_BASE_URL=https://$DOMAIN`
- `MAIL_DOMAIN=$DOMAIN`
- `MAIL_DOMAINS=$DOMAIN`
- `POSTGRES_PASSWORD`
- `DATABASE_URL` 中的密码
- `ADMIN_USERNAME`
- `ADMIN_PASSWORD`
- `INGEST_TOKEN`
- 可选 `SPACESHIP_API_KEY`
- 可选 `SPACESHIP_API_SECRET`
- 可选 `SPACESHIP_DNS_DOMAIN=$DOMAIN`
- 可选 `SPACESHIP_AUTO_REGISTER_TXT_PREFIX=openai-domain-verification=`
- 可选 `SPACESHIP_AUTO_REGISTER_PARENTS=exa,exe`

不得把真实密码输出到对话中。

如果部署者提供 Spaceship API，只要求只读权限：`domains:read` 和
`dnsrecords:read`。同步功能需要 API Key、API Secret、DNS 域名和 TXT 前缀都显式配置。
`SPACESHIP_AUTO_REGISTER_PARENTS` 控制扫描父级，例如 `exa,exe`。不要要求或保存
`dnsrecords:write`，当前功能不需要写 DNS。

启动应用：

```bash
ssh "$SSH_HOST" "cd $APP_DIR && docker compose -f docker-compose.maildrop.yml build app"
ssh "$SSH_HOST" "cd $APP_DIR && docker compose -f docker-compose.maildrop.yml up -d postgres"
ssh "$SSH_HOST" "cd $APP_DIR && docker compose -f docker-compose.maildrop.yml run --rm app alembic upgrade head"
ssh "$SSH_HOST" "cd $APP_DIR && docker compose -f docker-compose.maildrop.yml up -d app"
```

配置 Postfix：

```bash
ssh "$SSH_HOST" "cd $APP_DIR && \
  useradd -r -s /usr/sbin/nologin mailapi || true && \
  install -m 0755 deploy/postfix/mail-api-ingest /usr/local/bin/mail-api-ingest && \
  tmp_env=\$(mktemp) && \
  printf 'INGEST_TOKEN=%s\n' \"\$(grep '^INGEST_TOKEN=' .env.maildrop | cut -d= -f2-)\" > \"\$tmp_env\" && \
  install -o root -g mailapi -m 0640 \"\$tmp_env\" /etc/mail-api-ingest.env && \
  rm -f \"\$tmp_env\""
```

Postfix 配置模板中的 `aiprot.space` 是示例域名。部署到别的域名时，必须先替换为部署者域名，再安装到 `/etc/postfix`。

配置 Caddy：

```bash
ssh "$SSH_HOST" "cd $APP_DIR && install -m 0644 deploy/caddy/Caddyfile.maildrop /etc/caddy/Caddyfile && caddy validate --config /etc/caddy/Caddyfile && systemctl reload caddy"
```

Caddy 模板里的域名同样必须替换。

## 验证门禁

部署完成前必须运行：

```bash
.venv/bin/python -m pytest tests/maildrop -q
git diff --check
```

服务器侧必须验证：

```bash
curl -fsS http://127.0.0.1:8000/api/health
curl -fsS https://<domain>/api/health
curl -s -o /dev/null -w '%{http_code}\n' https://<domain>/admin
curl -s -o /dev/null -w '%{http_code}\n' https://<domain>/internal/ingest
docker compose -f /opt/maildrop/docker-compose.maildrop.yml ps
systemctl is-active postfix
ss -ltn | grep ':25 '
```

期望：

- 本地测试通过。
- `git diff --check` 无输出。
- HTTP health 正常。
- `/admin` 未认证为 `401`。
- `/internal/ingest` 公网为 `404`。
- Docker app/postgres healthy。
- Postfix active。
- 服务器监听 SMTP 25。

DNS 生效后，发送真实邮件到后台生成的邮箱，并用 API 链接确认读到最新邮件。

## 安全约束

- 不要提交 `.env`、`.env.maildrop`、数据库备份、日志或导出的 API token。
- 不要在回复中输出真实 `ADMIN_PASSWORD`、`POSTGRES_PASSWORD`、`INGEST_TOKEN`。
- 不要让 Caddy 对公开 inbox API 加全站 Basic Auth，否则 API 链接无法直接打开。
- 不要把 `/internal/*` 暴露公网。
- 不要启用会记录完整 query string 的访问日志；API token 在 query string 中。
- 不要用 `git reset --hard` 或覆盖部署者未确认的文件。

## 常用后续操作

后台入口：

```text
https://<domain>/admin
```

收件管理器：

```text
https://<domain>/xxxmailmanage
```

子域名管理：

```text
https://<domain>/admin/subdomains
```

新增 `c.exa.<domain>` 时，在子域名管理里输入 `c`。新增 `exe.<domain>` 时输入
完整后缀 `exe.<domain>`；新增 `c.exe.<domain>` 时可输入 `c.exe`。
DNS 仍需配置对应 MX，后台登记不会自动修改 DNS。

如果配置了 Spaceship API，可点击“从 Spaceship TXT 记录同步”。AI 应提醒部署者：
该按钮只读取 `SPACESHIP_AUTO_REGISTER_PARENTS` 父级下的 `openai-domain-verification=` TXT，
不会修改 Spaceship DNS。
