# Maildrop AI 自动部署指南

这份文档给 Codex、Claude Code、Cursor Agent 等 AI 部署代理读取。目标是让 AI
可以在拿到服务器 SSH、域名和 IP 后，自动完成部署，同时明确哪些信息必须由部署者
自己提供或手动配置。

所有对用户的说明默认使用简体中文。

## 1. 部署原则

- 不要输出真实密码、token、API Key、API Secret。
- 不要提交 `.env.maildrop`、`.env`、数据库备份、日志或导出的 API 链接。
- 不要覆盖服务器已有 `.env.maildrop`。如果只是新增字段，必须合并指定 key。
- 不要使用 `git reset --hard`、`git checkout --` 等破坏性命令，除非用户明确要求。
- 不要让 Caddy 对全站加 Basic Auth。公开 API 链接需要能直接访问。
- 必须让 Caddy 屏蔽公网 `/internal/*`。
- Spaceship API 只需要读权限，不要要求 `dnsrecords:write`。

## 2. 部署前必须向用户收集

必须有：

```text
DOMAIN=example.com
SERVER_IP=203.0.113.10
SSH_HOST=root@203.0.113.10
APP_DIR=/opt/maildrop
ADMIN_USERNAME=admin
```

需要生成或由用户提供：

```text
POSTGRES_PASSWORD=<随机强密码>
ADMIN_PASSWORD=<随机强密码>
INGEST_TOKEN=<随机强token>
```

可选：

```text
MAIL_DOMAINS=example.com,ssn.example.com,sso.example.com
MAIL_REGISTERED_SUBDOMAINS=a.exa.example.com,b.exa.example.com,exe.example.com,c.exe.example.com
SPACESHIP_API_KEY=<只读APIKey>
SPACESHIP_API_SECRET=<只读APISecret>
SPACESHIP_DNS_DOMAIN=example.com
SPACESHIP_AUTO_REGISTER_TXT_PREFIX=openai-domain-verification=
SPACESHIP_AUTO_REGISTER_PARENTS=exa,exe
```

如果用户没有给固定子域名：

```text
MAIL_DOMAINS=<DOMAIN>
```

如果用户没有给预置登记式子域名：

```text
MAIL_REGISTERED_SUBDOMAINS=
```

## 3. 必须提醒用户手动完成的 DNS

AI 通常不能登录用户 DNS 后台。部署前或部署过程中必须明确提醒用户添加：

```text
mail.example.com.      A    203.0.113.10
example.com.           MX   10 mail.example.com.
example.com.           TXT  "v=spf1 -all"
_dmarc.example.com.    TXT  "v=DMARC1; p=reject; sp=reject; adkim=s; aspf=s"
```

如果用户要用 `*.exa.example.com`：

```text
*.exa.example.com.     MX   10 mail.example.com.
*.exa.example.com.     TXT  "v=spf1 -all"
exa.example.com.       MX   10 mail.example.com.
exa.example.com.       TXT  "v=spf1 -all"
```

如果用户要用其他登记式后缀，例如 `exe.example.com` 或 `c.exe.example.com`，
也要提醒添加对应 MX/TXT，例如：

```text
exe.example.com.       MX   10 mail.example.com.
exe.example.com.       TXT  "v=spf1 -all"
*.exe.example.com.     MX   10 mail.example.com.
*.exe.example.com.     TXT  "v=spf1 -all"
```

还要提醒：

- 删除旧的 Spaceship Email Forwarding Free MX/TXT。
- 不要同时保留两个邮件服务的 MX。
- 云服务器安全组开放 TCP `25`、`80`、`443`。

## 4. 本地仓库检查

部署前先确认当前仓库：

```bash
git status --short --branch
rg --files
```

如果有用户未提交改动，不能随意覆盖。只同步项目部署所需文件，排除敏感文件和缓存。

## 5. 同步代码到服务器

```bash
ssh "$SSH_HOST" "mkdir -p '$APP_DIR'"
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

## 6. 创建或合并 `.env.maildrop`

新部署可以复制模板：

```bash
ssh "$SSH_HOST" "cd '$APP_DIR' && test -f .env.maildrop || cp .env.maildrop.example .env.maildrop"
```

然后写入这些 key：

```dotenv
APP_BASE_URL=https://example.com
MAIL_DOMAIN=example.com
MAIL_DOMAINS=example.com
MAIL_REGISTERED_SUBDOMAINS=
DATABASE_URL=postgresql+psycopg://maildrop:<POSTGRES_PASSWORD>@postgres:5432/maildrop
ADMIN_USERNAME=admin
ADMIN_PASSWORD=<ADMIN_PASSWORD>
INGEST_TOKEN=<INGEST_TOKEN>
MAX_MESSAGE_BYTES=26214400
MESSAGE_RETENTION_DAYS=180
UNASSIGNED_RETENTION_DAYS=30
SPACESHIP_API_KEY=
SPACESHIP_API_SECRET=
SPACESHIP_DNS_DOMAIN=example.com
SPACESHIP_AUTO_REGISTER_TXT_PREFIX=openai-domain-verification=
SPACESHIP_AUTO_REGISTER_PARENTS=exa,exe

POSTGRES_DB=maildrop
POSTGRES_USER=maildrop
POSTGRES_PASSWORD=<POSTGRES_PASSWORD>
```

更新已有服务器时，不要整文件覆盖。只合并本次要改的 key，并保留其他未知 key。

## 7. 安装服务器依赖

Ubuntu/Debian：

```bash
ssh "$SSH_HOST" "apt-get update && apt-get install -y docker.io docker-compose-plugin postfix caddy curl rsync"
ssh "$SSH_HOST" "systemctl enable --now docker"
```

如果安装 Postfix 时出现交互，选择：

```text
Internet Site
mail.example.com
```

## 8. 启动数据库和应用

```bash
ssh "$SSH_HOST" "cd '$APP_DIR' && docker compose -f docker-compose.maildrop.yml build app"
ssh "$SSH_HOST" "cd '$APP_DIR' && docker compose -f docker-compose.maildrop.yml up -d postgres"
ssh "$SSH_HOST" "cd '$APP_DIR' && docker compose -f docker-compose.maildrop.yml run --rm app alembic upgrade head"
ssh "$SSH_HOST" "cd '$APP_DIR' && docker compose -f docker-compose.maildrop.yml up -d app"
ssh "$SSH_HOST" "cd '$APP_DIR' && docker compose -f docker-compose.maildrop.yml ps"
```

## 9. 配置 Postfix

安装 pipe 脚本和 ingest token：

```bash
ssh "$SSH_HOST" "cd '$APP_DIR' && \
  useradd -r -s /usr/sbin/nologin mailapi || true && \
  install -m 0755 deploy/postfix/mail-api-ingest /usr/local/bin/mail-api-ingest && \
  tmp_env=\$(mktemp) && \
  printf 'INGEST_TOKEN=%s\n' \"\$(grep '^INGEST_TOKEN=' .env.maildrop | cut -d= -f2-)\" > \"\$tmp_env\" && \
  install -o root -g mailapi -m 0640 \"\$tmp_env\" /etc/mail-api-ingest.env && \
  rm -f \"\$tmp_env\""
```

把模板里的 `aiprot.space` 替换成 `$DOMAIN` 后再应用：

```bash
replacement_domain="$(printf '%s' "$DOMAIN" | sed 's/[&\\/]/\\&/g')"
ssh "$SSH_HOST" "cd '$APP_DIR' && \
  sed 's/aiprot\\.space/$replacement_domain/g' deploy/postfix/main.cf.maildrop > /tmp/main.cf.maildrop && \
  while IFS= read -r line; do case \"\$line\" in ''|'#'*) continue ;; esac; postconf -e \"\$line\"; done < /tmp/main.cf.maildrop && \
  sed 's/aiprot\\.space/$replacement_domain/g' deploy/postfix/virtual_mailbox_domains_regexp > /etc/postfix/virtual_mailbox_domains_regexp && \
  sed 's/aiprot\\.space/$replacement_domain/g' deploy/postfix/virtual_mailbox_regexp > /etc/postfix/virtual_mailbox_regexp && \
  postconf -M -e 'mailapi/unix=mailapi unix - n n - - pipe flags=Rq user=mailapi argv=/usr/local/bin/mail-api-ingest \${recipient}' && \
  postfix check && \
  systemctl restart postfix && \
  systemctl enable postfix"
```

不要把未替换的 `aiprot.space`
模板直接安装到新服务器。

## 10. 配置 Caddy

同样先替换域名：

```bash
replacement_domain="$(printf '%s' "$DOMAIN" | sed 's/[&\\/]/\\&/g')"
ssh "$SSH_HOST" "cd '$APP_DIR' && \
  sed 's/aiprot\\.space/$replacement_domain/g' deploy/caddy/Caddyfile.maildrop > /etc/caddy/Caddyfile && \
  caddy validate --config /etc/caddy/Caddyfile && \
  systemctl reload caddy"
```

不要把未替换的 `aiprot.space` Caddy 模板直接安装到新服务器。

## 11. 验证门禁

本地必须运行：

```bash
.venv/bin/python -m pytest tests/maildrop -q
git diff --check
```

如果本地存在已填写生产值的 `.env.maildrop`，测试可能读取到真实
`MAIL_DOMAINS` 或 `SPACESHIP_*` 配置。此时用空值覆盖可选项后重跑：

```bash
MAIL_DOMAINS='' MAIL_REGISTERED_SUBDOMAINS='' SPACESHIP_API_KEY='' SPACESHIP_API_SECRET='' SPACESHIP_DNS_DOMAIN='' SPACESHIP_AUTO_REGISTER_TXT_PREFIX='' SPACESHIP_AUTO_REGISTER_PARENTS='' .venv/bin/python -m pytest tests/maildrop -q
```

服务器必须运行：

```bash
ssh "$SSH_HOST" "cd '$APP_DIR' && docker compose -f docker-compose.maildrop.yml ps"
ssh "$SSH_HOST" "curl -fsS http://127.0.0.1:8000/api/health"
ssh "$SSH_HOST" "systemctl is-active postfix"
ssh "$SSH_HOST" "ss -ltn | grep ':25 '"
curl -fsS "https://$DOMAIN/api/health"
curl -s -o /dev/null -w '%{http_code}\n' "https://$DOMAIN/admin"
curl -s -o /dev/null -w '%{http_code}\n' "https://$DOMAIN/internal/ingest"
```

期望：

- `app` 和 `postgres` healthy。
- 本机 health 成功。
- 公网 health 成功。
- `/admin` 未认证返回 `401`。
- `/internal/ingest` 公网返回 `404`。
- Postfix active。
- SMTP `25` 正在监听。

如果仓库中有 `scripts/maildrop-production-check.sh`，优先运行：

```bash
scripts/maildrop-production-check.sh "$DOMAIN" "$SSH_HOST" "$SERVER_IP"
```

## 12. Spaceship TXT 自动登记验收

只有当用户配置了 Spaceship API Key/Secret、DNS 域名和 TXT 前缀才执行。

后台入口：

```text
https://<domain>/admin/subdomains
```

验证点：

- “从 Spaceship TXT 记录同步”按钮不是 disabled。
- 点击后 HTTP 返回 `200`。
- 返回文案可能是“新增 N 个”或“没有新增子域名；跳过 N 个”。

如果返回 502，检查 Spaceship API 权限、Key/Secret、`SPACESHIP_DNS_DOMAIN`。

## 13. 部署完成后告诉用户

最终回复必须包含：

- 后台地址：`https://<domain>/admin`
- 收件管理器地址：`https://<domain>/xxxmailmanage`
- 子域名管理地址：`https://<domain>/admin/subdomains`
- 已完成的验证命令和结果摘要。
- 哪些事项仍需用户自行确认，例如 DNS 传播或真实外部邮件投递。

不要在最终回复中包含任何真实密码、token、API Key 或 API Secret。
