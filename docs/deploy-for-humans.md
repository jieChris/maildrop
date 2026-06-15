# Maildrop 傻瓜部署填写清单

这份文档给人类部署者看。你只需要先把“需要填写的信息”准备好，再按
`docs/deploy-from-scratch.md` 执行部署命令。

示例值统一使用：

- 域名：`example.com`
- 服务器 IP：`203.0.113.10`
- 项目目录：`/opt/maildrop`

部署时把示例值换成你自己的。

## 1. 你需要先准备什么

| 项目 | 你的值 | 说明 |
| --- | --- | --- |
| 主域名 | `example.com` | 用来访问后台和收信，例如 `https://example.com/admin` |
| 服务器公网 IP | `203.0.113.10` | DNS 的 A 记录要指向它 |
| SSH 登录方式 | `root@203.0.113.10` | 也可以是本机 SSH alias，例如 `maildrop` |
| 后台用户名 | `admin` | 登录 `/admin` 和 `/xxxmailmanage` |
| 后台密码 | 自己生成 | 不要用示例密码 |
| 数据库密码 | 自己生成 | `POSTGRES_PASSWORD` 和 `DATABASE_URL` 里必须一致 |
| Ingest Token | 自己生成 | Postfix 投递邮件到应用时使用 |
| 固定邮箱后缀 | 可空 | 例如 `ssn.example.com,sso.example.com` |
| 登记式子域名 | 可空 | 例如 `a.exa.example.com,exe.example.com,c.exe.example.com` |
| Spaceship API Key | 可空 | 只用于读取 TXT 自动登记子域名 |
| Spaceship API Secret | 可空 | 只用于读取 TXT 自动登记子域名 |

推荐在服务器上生成三个随机密钥：

```bash
openssl rand -hex 24
openssl rand -hex 24
openssl rand -hex 24
```

分别填给：

- `POSTGRES_PASSWORD`
- `ADMIN_PASSWORD`
- `INGEST_TOKEN`

## 2. DNS 应该怎么填

最小可用配置：

| 主机 | 类型 | 值 | 优先级 |
| --- | --- | --- | --- |
| `mail` | `A` | `203.0.113.10` | 留空 |
| `@` | `MX` | `mail.example.com.` | `10` |
| `@` | `TXT` | `v=spf1 -all` | 留空 |
| `_dmarc` | `TXT` | `v=DMARC1; p=reject; sp=reject; adkim=s; aspf=s` | 留空 |

如果你要使用 `a.exa.example.com`、`b.exa.example.com` 这种登记式邮箱后缀，再加：

| 主机 | 类型 | 值 | 优先级 |
| --- | --- | --- | --- |
| `*.exa` | `MX` | `mail.example.com.` | `10` |
| `*.exa` | `TXT` | `v=spf1 -all` | 留空 |
| `exa` | `MX` | `mail.example.com.` | `10` |
| `exa` | `TXT` | `v=spf1 -all` | 留空 |

如果你还要使用 `exe.example.com` 或 `c.exe.example.com`，也要加对应 DNS：

| 主机 | 类型 | 值 | 优先级 |
| --- | --- | --- | --- |
| `exe` | `MX` | `mail.example.com.` | `10` |
| `exe` | `TXT` | `v=spf1 -all` | 留空 |
| `*.exe` | `MX` | `mail.example.com.` | `10` |
| `*.exe` | `TXT` | `v=spf1 -all` | 留空 |

注意：

- MX 的值建议保留最后的点：`mail.example.com.`
- 如果开过 Spaceship 的 Email Forwarding Free，删除它自动生成的 MX/TXT。
- 同一个域名不要同时保留 Spaceship 转发 MX 和 Maildrop MX。
- 服务器防火墙和云服务商安全组要开放 TCP `25`、`80`、`443`。

## 3. `.env.maildrop` 怎么填

部署时复制模板：

```bash
cp .env.maildrop.example .env.maildrop
```

然后至少修改这些项：

```dotenv
APP_BASE_URL=https://example.com
MAIL_DOMAIN=example.com
DATABASE_URL=postgresql+psycopg://maildrop:你的数据库密码@postgres:5432/maildrop
ADMIN_USERNAME=admin
ADMIN_PASSWORD=你的后台密码
INGEST_TOKEN=你的ingest随机token

POSTGRES_DB=maildrop
POSTGRES_USER=maildrop
POSTGRES_PASSWORD=你的数据库密码
```

`DATABASE_URL` 里的密码必须和 `POSTGRES_PASSWORD` 完全一致。

## 4. 邮箱后缀相关配置

### `MAIL_DOMAIN`

主域名，只填一个：

```dotenv
MAIL_DOMAIN=example.com
```

系统会根据它保留兼容默认父级：输入 `c` 会登记为 `c.exa.example.com`。

### `MAIL_DOMAINS`

固定邮箱后缀列表。后台批量生成邮箱时可以选择这些后缀。

只用主域名：

```dotenv
MAIL_DOMAINS=example.com
```

还要使用固定子域名：

```dotenv
MAIL_DOMAINS=example.com,ssn.example.com,sso.example.com,wow.example.com
```

固定子域名需要 DNS 也有对应 MX，或 DNS 有能覆盖它们的 MX。

### `MAIL_REGISTERED_SUBDOMAINS`

预置的登记式后缀。可以为空：

```dotenv
MAIL_REGISTERED_SUBDOMAINS=
```

如果一开始就要允许这些后缀：

```dotenv
MAIL_REGISTERED_SUBDOMAINS=a.exa.example.com,b.exa.example.com,exe.example.com,c.exe.example.com
```

后续也可以在后台新增：

```text
https://example.com/admin/subdomains
```

后台新增的子域名会写入数据库，不会自动写回 `.env.maildrop`。

后台新增时：

- 输入 `c`：新增 `c.exa.example.com`。
- 输入 `exe.example.com`：新增 `exe.example.com`。
- 输入 `c.exe`：新增 `c.exe.example.com`。

## 5. Spaceship API 自动同步怎么填

如果你不需要自动读取 Spaceship TXT，可以留空：

```dotenv
SPACESHIP_API_KEY=
SPACESHIP_API_SECRET=
SPACESHIP_DNS_DOMAIN=example.com
SPACESHIP_AUTO_REGISTER_TXT_PREFIX=openai-domain-verification=
SPACESHIP_AUTO_REGISTER_PARENTS=exa,exe
```

如果要用后台按钮自动登记 OpenAI 验证子域名，API Key/Secret、DNS 域名和 TXT 前缀都要填；父级列表按需要配置：

```dotenv
SPACESHIP_API_KEY=你的只读APIKey
SPACESHIP_API_SECRET=你的只读APISecret
SPACESHIP_DNS_DOMAIN=example.com
SPACESHIP_AUTO_REGISTER_TXT_PREFIX=openai-domain-verification=
SPACESHIP_AUTO_REGISTER_PARENTS=exa,exe
```

Spaceship API 权限只需要：

```text
domains:read
dnsrecords:read
```

当前系统只读取 TXT 记录，不创建、不修改、不删除 DNS 记录，所以不需要
`dnsrecords:write`。

`SPACESHIP_AUTO_REGISTER_PARENTS` 是要自动扫描的父级后缀列表。可以写短名：

```dotenv
SPACESHIP_AUTO_REGISTER_PARENTS=exa,exe
```

也可以写完整域名：

```dotenv
SPACESHIP_AUTO_REGISTER_PARENTS=exa.example.com,exe.example.com
```

后台同步入口：

```text
https://example.com/admin/subdomains
```

点击“从 Spaceship TXT 记录同步”后，系统会查找类似：

```text
urxg.exa.example.com TXT openai-domain-verification=xxxx
```

然后把 `urxg.exa.example.com` 登记进系统。

## 6. 部署完成后怎么访问

后台：

```text
https://example.com/admin
```

收件管理器：

```text
https://example.com/xxxmailmanage
```

子域名管理：

```text
https://example.com/admin/subdomains
```

健康检查：

```text
https://example.com/api/health
```

## 7. 最后验收清单

部署者或 AI 代理需要确认：

- `https://example.com/api/health` 能打开。
- 未登录访问 `https://example.com/admin` 返回登录框。
- 公网访问 `https://example.com/internal/ingest` 返回 `404`。
- Docker 中 `app` 和 `postgres` 都是 healthy。
- 服务器 Postfix 是 active。
- 服务器监听 SMTP `25` 端口。
- 在后台生成一个邮箱，向它发邮件后，API 链接能读到最新邮件。

如果收不到邮件，优先检查：

- MX 是否还指向旧的邮箱转发服务。
- `mail.example.com` A 记录是否指向服务器 IP。
- TCP `25` 是否被防火墙或云服务商封锁。
- Postfix 是否正在运行。
