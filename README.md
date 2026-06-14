# Maildrop 轻量收信服务

Maildrop 是一个轻量自托管收信服务，用 Postfix 接收 catch-all 邮件，用 FastAPI 提供中文管理后台和 tokenized API 链接。它适合把大量临时邮箱集中管理，并把每个邮箱导出为可直接访问最新邮件的 API 链接。

## 功能

- SMTP 接收：宿主机 Postfix。
- 应用：Python 3.12 + FastAPI。
- 数据库：PostgreSQL 16。
- 反向代理：Caddy。
- 后台：中文 Jinja2 管理页面，Basic Auth。
- API：每个邮箱前缀有独立 token 链接，可直接访问最新无格式邮件。
- 未登记前缀：进入“未登记邮件”列表，不自动创建 alias。
- 管理分类：后台按 `未导出`、`已导出`、`已删除` 管理邮箱别名。
- 收件管理器：`/xxxmailmanage` 可导入邮箱和 API 链接，并标记 `待消耗`、`已消耗`、`错误`。
- 子域名管理：后台可登记 `*.exa.<domain>` 风格的子域名后缀，并分别批量生成和管理。

当前仓库中的生产示例使用 `aiprot.space`。如果部署到别的域名，请按 `docs/deploy-from-scratch.md` 替换域名和 IP。

## Maildrop 文件

- `pyproject.toml`：Python 包和依赖。
- `src/maildrop/`：Maildrop 应用代码。
- `tests/maildrop/`：Maildrop 单元和接口测试。
- `Dockerfile`：FastAPI 应用镜像。
- `docker-compose.maildrop.yml`：Maildrop + PostgreSQL 部署。
- `.env.maildrop.example`：可提交的 Maildrop 环境变量模板。
- `docs/deploy-from-scratch.md`：给新服务器/新域名使用的通用部署指南。
- `docs/spaceship-dns.md`：Spaceship DNS 配置和 MX 冲突处理指南。
- `AGENTS.md`：给 Codex/AI 部署代理读取的自动部署说明。
- `docs/maildrop-ops.md`：当前生产运维、备份、清理和验收说明。
- `MAILDROP_MAIN.md`：当前状态、架构决策和推进记录。
- `docs/superpowers/plans/2026-06-12-lightweight-mail-api.md`：主实施计划。

## 本地测试

```bash
.venv/bin/python -m pytest tests/maildrop -v
```

## Docker Compose 配置检查

```bash
cp .env.maildrop.example .env.maildrop
python - <<'PY'
from pathlib import Path

p = Path(".env.maildrop")
text = p.read_text()
text = text.replace("change-postgres-password", "local-postgres-secret")
text = text.replace("change-admin-password", "local-admin-secret")
text = text.replace("change-ingest-token", "local-ingest-secret")
p.write_text(text)
PY
docker compose -f docker-compose.maildrop.yml config --quiet
```

## 本地启动 Maildrop

```bash
docker compose -f docker-compose.maildrop.yml up -d --build
docker compose -f docker-compose.maildrop.yml ps
```

启动后应用只绑定到宿主机本机：

```text
http://127.0.0.1:8000
```

生产访问应由 Caddy 代理到 `127.0.0.1:8000`，并屏蔽 `/internal/*`。
Maildrop 应用自身保护 `/admin`，Caddy 不再对整站加 Basic Auth，否则公开 API 链接无法直接访问。

## 公开 API

已登记邮箱前缀的最新邮件纯文本 API：

```text
https://example.com/api/inbox/{prefix}/latest.txt?token={token}
```

JSON API：

```text
https://example.com/api/inbox/{prefix}/latest.json?token={token}
https://example.com/api/inbox/{prefix}/messages.json?token={token}&limit=20
```

API token 只在批量生成、后台轮换 token 或导出 API 链接后显示一次。已有别名如果丢失链接，可在后台对该别名执行“轮换 token”，旧链接会立即失效。

后台支持勾选邮箱后导出，也支持导出全部邮箱。导出会为相关邮箱重新生成 token，并下载如下格式的文本文件：

```text
user001@example.com https://example.com/api/inbox/user001/latest.txt?token=...
user002@example.com https://example.com/api/inbox/user002/latest.txt?token=...
```

导出成功后，相关邮箱会进入 `已导出` 分类。未导出过的邮箱保留在 `未导出` 分类。

后台支持软删除邮箱。删除后邮箱进入 `已删除` 分类，API 链接立即返回 403，历史邮件保留；后续发到该前缀的邮件会进入“未登记邮件”，原因记录为 `alias_deleted`。已删除邮箱不会被“导出全部”包含。

## 收件管理器

管理入口：

```text
https://example.com/xxxmailmanage
```

使用和 `/admin` 相同的 Basic Auth。可以直接粘贴 Maildrop 导出的邮箱和 API 链接，支持以下格式：

```text
user001@example.com https://example.com/api/inbox/user001/latest.txt?token=...
user002@example.com----https://example.com/api/inbox/user002/latest.txt?token=...
```

导入后每条记录可标记为 `待消耗`、`已消耗`、`错误`，也可以通过服务端请求 API 链接查看最新纯文本邮件。重复导入同一个邮箱会更新 API 链接，但保留原状态和备注。

生产 Docker 启动已关闭 Uvicorn access log，避免 query token 写入应用访问日志。

## 从零部署

见 `docs/deploy-from-scratch.md`。核心流程是：

1. 配置 DNS：`mail.<domain>` A 记录、根域 MX、SPF、DMARC。
2. 复制 `.env.maildrop.example` 为 `.env.maildrop` 并填入域名、数据库密码、后台密码和 ingest token。
3. 用 Docker Compose 启动 PostgreSQL 和 FastAPI app。
4. 运行 Alembic 迁移。
5. 配置 Postfix pipe 到 `/internal/ingest`。
6. 配置 Caddy 反代并屏蔽 `/internal/*`。
7. 登录 `/admin` 批量生成邮箱，向邮箱投递邮件并打开 API 链接验收。

当前 `deploy/postfix/*` 和 `deploy/caddy/Caddyfile.maildrop` 仍以 `aiprot.space` 为模板示例；部署到其他域名时需要替换。

## EmailEngine 历史配置

以下文件仍保留，作为迁移前历史和必要时的回滚参考：

- `docker-compose.yml`：EmailEngine + Redis。Redis 按数据库使用，开启持久化和 `noeviction`。
- `.env.example`：EmailEngine 环境变量模板。
- `overrides/emailengine/`：管理后台汉化覆盖层。
- `tests/admin-zh.test.js`：EmailEngine 汉化脚本测试。

当前生产流量由 Caddy 代理到 Maildrop 的 `127.0.0.1:8000`。EmailEngine 容器已停止但卷仍保留，以下地址现在指向 Maildrop：

```text
https://aiprot.space
https://www.aiprot.space
https://engine.aiprot.space
```

EmailEngine 回滚启动命令：

```bash
ssh root@167.71.29.22 'cd /opt/emailengine && docker compose up -d'
```

## License

MIT
