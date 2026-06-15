# Maildrop 从零部署指南

这份文档用于把本项目部署到一台新的 Linux 服务器。示例假设：

- 域名：`example.com`
- 服务器公网 IP：`203.0.113.10`
- 项目路径：`/opt/maildrop`
- 系统：Ubuntu/Debian

部署时把示例域名和 IP 替换成你自己的值。

如果你只是想知道“我应该填什么”，先看 `docs/deploy-for-humans.md`。
如果你要把部署交给 AI/Codex 执行，先让它读取 `docs/deploy-for-ai.md`。

## 1. DNS

在 DNS 服务商添加。如果使用 Spaceship，界面填写方式和冲突处理见
`docs/spaceship-dns.md`。

```text
mail.example.com.      A    203.0.113.10
example.com.           MX   10 mail.example.com.
example.com.           TXT  "v=spf1 -all"
_dmarc.example.com.    TXT  "v=DMARC1; p=reject; sp=reject; adkim=s; aspf=s"
```

如果要使用登记式子域名邮箱，例如 `a.exa.example.com`：

```text
*.exa.example.com.     MX   10 mail.example.com.
*.exa.example.com.     TXT  "v=spf1 -all"
exa.example.com.       MX   10 mail.example.com.
exa.example.com.       TXT  "v=spf1 -all"
```

如果还要使用 `exe.example.com` 或 `c.exe.example.com`，也要添加：

```text
exe.example.com.       MX   10 mail.example.com.
exe.example.com.       TXT  "v=spf1 -all"
*.exe.example.com.     MX   10 mail.example.com.
*.exe.example.com.     TXT  "v=spf1 -all"
```

## 2. 安装系统依赖

```bash
apt-get update
apt-get install -y docker.io docker-compose-plugin postfix caddy curl rsync
systemctl enable --now docker
```

安装 Postfix 时选择 `Internet Site`，主机名可填 `mail.example.com`。

## 3. 上传代码

```bash
mkdir -p /opt/maildrop
rsync -az --delete ./ root@203.0.113.10:/opt/maildrop/
ssh root@203.0.113.10
cd /opt/maildrop
```

## 4. 配置环境变量

```bash
cp .env.maildrop.example .env.maildrop
openssl rand -hex 24
openssl rand -hex 24
openssl rand -hex 24
nano .env.maildrop
```

至少修改：

```dotenv
APP_BASE_URL=https://example.com
MAIL_DOMAIN=example.com
MAIL_DOMAINS=example.com
MAIL_REGISTERED_SUBDOMAINS=
POSTGRES_PASSWORD=<随机值>
DATABASE_URL=postgresql+psycopg://maildrop:<同一个随机值>@postgres:5432/maildrop
ADMIN_USERNAME=admin
ADMIN_PASSWORD=<随机值>
INGEST_TOKEN=<随机值>
SPACESHIP_API_KEY=
SPACESHIP_API_SECRET=
SPACESHIP_DNS_DOMAIN=example.com
SPACESHIP_AUTO_REGISTER_TXT_PREFIX=openai-domain-verification=
```

如果已经确定要预置子域名，可设置：

```dotenv
MAIL_REGISTERED_SUBDOMAINS=a.exa.example.com,b.exa.example.com
```

后续也可以在后台 `/admin/subdomains` 继续新增。

如果要让后台从 Spaceship 自动同步 OpenAI TXT 验证子域名，必须显式配置
`SPACESHIP_API_KEY`、`SPACESHIP_API_SECRET`、`SPACESHIP_DNS_DOMAIN` 和
`SPACESHIP_AUTO_REGISTER_TXT_PREFIX`。API Key 只需要 `domains:read` 和
`dnsrecords:read` 权限，不需要写权限。Spaceship 具体 DNS 和 API 配置见
`docs/spaceship-dns.md`。

## 5. 启动数据库和应用

```bash
docker compose -f docker-compose.maildrop.yml build app
docker compose -f docker-compose.maildrop.yml up -d postgres
docker compose -f docker-compose.maildrop.yml run --rm app alembic upgrade head
docker compose -f docker-compose.maildrop.yml up -d app
docker compose -f docker-compose.maildrop.yml ps
curl -fsS http://127.0.0.1:8000/api/health
```

## 6. 配置 Postfix

安装本地投递脚本和 token：

```bash
useradd -r -s /usr/sbin/nologin mailapi || true
install -m 0755 deploy/postfix/mail-api-ingest /usr/local/bin/mail-api-ingest
tmp_env="$(mktemp)"
printf 'INGEST_TOKEN=%s\n' "$(grep '^INGEST_TOKEN=' .env.maildrop | cut -d= -f2-)" > "$tmp_env"
install -o root -g mailapi -m 0640 "$tmp_env" /etc/mail-api-ingest.env
rm -f "$tmp_env"
```

把 `deploy/postfix/main.cf.maildrop` 中的 `aiprot.space` 替换为你的域名后应用：

```bash
while IFS= read -r line; do
  case "$line" in
    ''|'#'*) continue ;;
  esac
  postconf -e "$line"
done < deploy/postfix/main.cf.maildrop
```

如果使用主域下的登记式子域名，也要把这两个文件中的 `aiprot.space` 替换为你的域名：

```bash
install -m 0644 deploy/postfix/virtual_mailbox_domains_regexp /etc/postfix/virtual_mailbox_domains_regexp
install -m 0644 deploy/postfix/virtual_mailbox_regexp /etc/postfix/virtual_mailbox_regexp
```

配置 pipe transport：

```bash
postconf -M -e 'mailapi/unix=mailapi unix - n n - - pipe flags=Rq user=mailapi argv=/usr/local/bin/mail-api-ingest ${recipient}'
postfix check
sudo -u mailapi sh -c '. /etc/mail-api-ingest.env; test -n "$INGEST_TOKEN"'
systemctl restart postfix
systemctl enable postfix
```

验证：

```bash
postmap -q 'example.com' regexp:/etc/postfix/virtual_mailbox_domains_regexp
postmap -q 'probe@example.com' regexp:/etc/postfix/virtual_mailbox_regexp
```

期望分别输出 `OK` 和 `catchall`。

## 7. 配置 Caddy

把 `deploy/caddy/Caddyfile.maildrop` 中的域名替换为你的域名，然后安装：

```bash
install -m 0644 deploy/caddy/Caddyfile.maildrop /etc/caddy/Caddyfile
caddy validate --config /etc/caddy/Caddyfile
systemctl reload caddy
```

Caddy 必须屏蔽公网 `/internal/*`，应用只应通过 Postfix 本机调用 ingest。

## 8. 验收

```bash
curl -fsS https://example.com/api/health
curl -s -o /dev/null -w '%{http_code}\n' https://example.com/admin
curl -s -o /dev/null -w '%{http_code}\n' https://example.com/internal/ingest
```

期望：

- `/api/health` 返回成功 JSON
- `/admin` 未认证返回 `401`
- `/internal/ingest` 返回 `404`

然后登录后台：

```text
https://example.com/admin
```

批量生成邮箱，向生成的邮箱发一封邮件，再打开生成的 API 链接确认能读到最新邮件。

## 9. 运维

- 备份、清理、Postfix 细节见 `docs/maildrop-ops.md`。
- 生产更新包含数据库结构变更时，先运行 `alembic upgrade head`，再重启 app。
- 不要提交 `.env.maildrop`、`.env`、数据库备份、日志或导出的 API token 文件。
