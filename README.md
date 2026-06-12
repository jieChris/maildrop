# Maildrop 轻量收信服务

这个目录是自研 Maildrop 轻量收信服务。当前生产环境已部署在服务器 `167.71.29.22`，用于接收 `aiprot.space` 的 catch-all 邮件，并按邮箱前缀提供中文管理后台和 tokenized API 链接。

## 当前目标

- 域名：`aiprot.space`
- SMTP 接收：宿主机 Postfix。
- 应用：Python 3.12 + FastAPI。
- 数据库：PostgreSQL 16。
- 反向代理：Caddy。
- 后台：中文 Jinja2 管理页面，Basic Auth。
- API：每个邮箱前缀有独立 token 链接，可直接访问最新无格式邮件。
- 未登记前缀：进入“未登记邮件”列表，不自动创建 alias。
- 当前生产状态：DNS 已切到 `mail.aiprot.space`，Postfix/Caddy/Maildrop 已通过生产检查和公网真实收信 smoke。

## Maildrop 文件

- `pyproject.toml`：Python 包和依赖。
- `src/maildrop/`：Maildrop 应用代码。
- `tests/maildrop/`：Maildrop 单元和接口测试。
- `Dockerfile`：FastAPI 应用镜像。
- `docker-compose.maildrop.yml`：Maildrop + PostgreSQL 部署。
- `.env.maildrop.example`：可提交的 Maildrop 环境变量模板。
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
https://aiprot.space/api/inbox/{prefix}/latest.txt?token={token}
```

JSON API：

```text
https://aiprot.space/api/inbox/{prefix}/latest.json?token={token}
https://aiprot.space/api/inbox/{prefix}/messages.json?token={token}&limit=20
```

API token 只在批量生成或后台轮换 token 后显示一次。已有别名如果丢失链接，可在后台对该别名执行“轮换 token”，旧链接会立即失效。

生产 Docker 启动已关闭 Uvicorn access log，避免 query token 写入应用访问日志。

## 服务器部署

```bash
rsync -av --exclude .git --exclude .venv --exclude .pytest_cache ./ root@167.71.29.22:/opt/maildrop/
ssh root@167.71.29.22 'cd /opt/maildrop && cp .env.maildrop.example .env.maildrop'
ssh root@167.71.29.22 'cd /opt/maildrop && $EDITOR .env.maildrop'
ssh root@167.71.29.22 'cd /opt/maildrop && docker compose -f docker-compose.maildrop.yml up -d --build'
ssh root@167.71.29.22 'cd /opt/maildrop && docker compose -f docker-compose.maildrop.yml ps'
```

Postfix、Caddy、DNS、生产验收、备份和清理策略见 `docs/maildrop-ops.md`。

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
