# Maildrop 主状态

## 目标

构建并部署一个轻量、长期可维护的自托管收信系统，替代需要许可证的 EmailEngine。

核心要求：

- 域名：`aiprot.space`
- 只收信，不发信/回复。
- MX 解析到自有服务器，由 Postfix 接收 catch-all 邮件。
- 已登记邮箱前缀进入对应收件箱。
- 未登记邮箱前缀进入“未登记邮件”列表，不自动创建别名。
- 管理后台支持批量生成随机邮箱前缀和对应 API 链接。
- 管理后台支持选择邮箱或全量导出邮箱及对应 API 链接；由于明文 token 不落库，导出会为相关邮箱轮换 token，旧链接立即失效。
- 管理后台支持按 `未导出`、`已导出`、`已删除` 分类管理邮箱；删除为软删除，历史邮件保留。
- 每个邮箱有独立 tokenized API，可直接访问最新邮件无格式文本。
- 系统需要能维护 1000+ 邮箱前缀。

## 当前架构决策

- SMTP 接收：宿主机 Postfix。
- 应用：Python 3.12 + FastAPI。
- 数据库：PostgreSQL。
- 后台：Jinja2 服务端页面，Basic Auth。
- 数据库初始化：应用代码不得在 import 时读取环境并创建全局 engine；使用可注入的 engine/session factory。生产 schema 变更后续必须引入 Alembic 迁移。
- Ingest 安全：`/internal/ingest` 只能给本机 Postfix 调用；Caddy 不应把该路径暴露公网。应用也必须校验 ingest token、收件域名和请求体大小。
- 存储控制：不能无限保存原始邮件；单封邮件大小、保留期、清理策略和备份说明都必须受控。
- 保留期策略：已登记消息默认保留 180 天，未登记/禁用/非法域名等 `unassigned_messages` 默认保留 30 天；边界为严格早于 UTC cutoff 的记录才删除，等于 cutoff 保留。
- 清理策略：只通过 CLI/cron 执行，不在应用启动时自动执行；生产 cron 必须使用 `flock` 防重入并记录日志；首次启用前先运行 `--dry-run`。
- 清理后必须同步修正 `Alias.message_count` 和 `Alias.last_message_at`，统计以 `messages` 表为准。
- Postfix 部署：脚本必须把临时失败映射为 exit 75，配置命令必须幂等，不能重复追加 `master.cf`。
- Postfix pipe 退出码契约：成功只允许 `0`；所有 ingest 临时失败统一 `75`；HTTP 状态必须显式映射，不能直接透传 `curl` 退出码。
- Postfix 配置只能用幂等方式安装：`postconf -e` 逐项更新 `main.cf`，`postconf -M -e` 管理 `master.cf`，禁止重复追加。
- Postfix `mailapi` 运行用户必须能读 ingest token；部署后必须执行 `sudo -u mailapi sh -c '. /etc/mail-api-ingest.env; test -n "$INGEST_TOKEN"'`。
- Postfix catch-all regexp 只负责“接受域内收件人”，lookup result 用常量；真实收件人以 envelope recipient 传入应用。
- Postfix pipe transport 必须设置 `mailapi_destination_recipient_limit = 1`。
- 邮件大小上限必须单一来源并保持一致：`.env.maildrop` 的 `MAX_MESSAGE_BYTES`、应用 ingest 限制和 Postfix `message_size_limit` 需要同步；生产应尽量在 SMTP 阶段拒绝超限邮件。
- API token：第一版保留 query token 以满足“直接点开 API 链接”，但必须降低泄漏风险：Caddy 不启用访问日志，Uvicorn 以 `--no-access-log` 启动，设置 `Referrer-Policy: no-referrer`；后台支持对已有 alias 轮换 token；后台导出 API 链接时也会轮换相关 alias 的 token。轮换后旧链接立即失效，新链接只显示/导出一次。
- Alias 生命周期：后台分类由 `exported_at` 和 `deleted_at` 派生；导出设置 `exported_at`，删除设置 `deleted_at` 且 `enabled=false`。删除 alias 后公开 API 返回 403，历史邮件保留，后续收信进入 `unassigned_messages` 并记录 `alias_deleted`。
- 生产 schema 变更：已引入 Alembic；涉及数据库结构的部署必须先运行 `alembic upgrade head`，再重启 app。
- 只收不发 DNS 策略：根域 SPF 使用 `-all`，DMARC 最终使用 `p=reject`；关闭 submission/smtps/认证发信面，只保留 25 入站。
- ASGI 启动：避免 `maildrop.app` 导入时读取环境；部署应使用 Uvicorn factory（例如 `maildrop.app:create_app --factory`）或专门的 ASGI 入口，而不是在模块底部定义全局 `app = create_app()`。
- API：
  - `/api/inbox/{prefix}/latest.txt?token=...`
  - `/api/inbox/{prefix}/latest.json?token=...`
  - `/api/inbox/{prefix}/messages.json?token=...&limit=20`
- 部署：Docker Compose 管理应用和 PostgreSQL，Caddy 负责 HTTPS。

## 计划文件

主实施计划：

- `docs/superpowers/plans/2026-06-12-lightweight-mail-api.md`

## 当前状态

- EmailEngine 已部署并加了双层保护，但最终目标是用 Maildrop 替代。
- Maildrop 已完成 Task 1：Python 项目骨架、配置对象、基础测试和本地开发环境。
- Maildrop 已完成 Task 2：数据库模型和注入式 session 层。
- Maildrop 已完成 Task 3：MIME 解析、收件人规范化、纯文本/HTML 正文提取。
- Maildrop 已完成 Task 4：alias/token repository、域名校验入库、未登记/禁用 alias 分流、批量 alias 单事务生成。
- Maildrop 已完成 Task 5：FastAPI ingest、公开 latest API、DB 注入式 app factory、本机 ingest 限制、请求体大小限制、Referrer-Policy、DB health。
- Maildrop 已完成 Task 6：中文管理后台、Basic Auth、CSRF、批量 alias 生成、搜索分页、未登记邮件列表、alias 最近邮件页面。
- Maildrop 已完成 Task 7 的部署文件主体：`.env.maildrop.example`、`Dockerfile`、`docker-compose.maildrop.yml`、README Maildrop 部署说明，以及模板/CSS package data 配置。
- Maildrop 已完成 Task 8 的 Postfix catch-all 配置和运维文档主体：Postfix main/master 配置、ingest pipe 脚本、幂等安装命令、备份恢复说明。
- Maildrop 已完成 Task 9 的本地 Caddy 配置准备：反代切换到 `127.0.0.1:8000`，公网屏蔽 `/internal/*`，移除旧的整站 Caddy Basic Auth。
- 服务器 `emailengine` / `167.71.29.22` 已部署 Maildrop、PostgreSQL、Postfix 和 Caddy cutover；EmailEngine 容器已停止但卷保留。
- 当前推进任务：Task 10 - Production Deployment and Smoke Test 已通过 DNS 和公网真实收信验收；统一初始提交已创建。
- 已新增可重复运行的生产验收脚本：`scripts/maildrop-production-check.sh aiprot.space emailengine 167.71.29.22`。2026-06-12 最新运行返回 `0`，DNS、HTTPS、Docker、Postfix 和公网 SMTP 25 连接均通过；脚本已加回归测试防止 Docker `unhealthy`、旧 MX 残留、DMARC `sp=reject` 误判为通过，并在 UDP DNS 查询超时或本机出站 SMTP 25 被阻断时自动回退。
- 已新增 DNS 切换后的真实公网收信验收脚本：`scripts/maildrop-public-smoke.py aiprot.space emailengine 167.71.29.22`。2026-06-12 最新运行通过，通过 SMTP 投递 `public-smoke-1781258315-4d3046ac@aiprot.space` 并确认进入 `unassigned_messages`；本机出站 SMTP 25 被阻断时会使用服务器侧投递 fallback。
- Spaceship 旧 MX/TXT 曾来自 `Email Forwarding Free` 预设记录组；用户已移除该预设记录并切到自建 Maildrop MX。若未来 Spaceship 再强制注入邮件转发预设，备选方案是把权威 DNS 从 Spaceship nameserver 切到 Cloudflare/其他 DNS 托管，再手动维护 Maildrop 所需记录。
- 已新增并部署保留期/清理策略：`MESSAGE_RETENTION_DAYS=180`、`UNASSIGNED_RETENTION_DAYS=30`，CLI 为 `python -m maildrop.cli cleanup [--dry-run]`，服务器已安装 `/etc/cron.d/maildrop-cleanup` 每日 03:17 执行并使用 `flock` 防重入。
- 已补齐 1000+ 前缀维护性回归测试：后台 alias 列表、搜索结果、未登记邮件和单 alias 邮件列表均有分页测试；已有 alias 可在后台轮换 token 并生成新的 API 链接。
- 已新增并部署后台导出功能：可勾选邮箱导出，或一键导出全部邮箱；导出格式为 `email latest.txt-url`，导出时为相关 alias 轮换 token，旧链接立即失效。
- 已新增并部署后台分类和软删除功能：`未导出`、`已导出`、`已删除` 分类，导出记录 `exported_at`，删除记录 `deleted_at` 并禁用 alias。

## 执行记录

- 2026-06-12：创建主状态文件，准备按计划从 Task 1 开始 TDD 实施。
- 2026-06-12：完成 Task 1。创建 `pyproject.toml`、`src/maildrop/config.py`、`tests/maildrop/test_config.py`，并用 `.venv/bin/python -m pytest tests/maildrop/test_config.py -v` 验证 2 个测试通过。首次红灯被本地缺少 pytest 阻断，随后创建 `.venv` 并安装开发依赖。
- 2026-06-12：多 agent 审查发现计划存在迁移、全局 DB 初始化、公网 ingest、容量控制、Postfix 幂等性、query token 泄漏等风险。已将关键修正写入“当前架构决策”，后续实现必须遵守。
- 2026-06-12：完成 Task 2。Worker 子 agent 创建 `src/maildrop/models.py`、`src/maildrop/db.py`、`tests/maildrop/conftest.py`、`tests/maildrop/test_models.py`，采用显式 engine/session factory 注入，SQLite 测试使用 `StaticPool`。
- 2026-06-12：完成 Task 3。创建 `src/maildrop/mailparse.py`、`tests/maildrop/test_mailparse.py`。组合验证 `.venv/bin/python -m pytest tests/maildrop/test_config.py tests/maildrop/test_models.py tests/maildrop/test_mailparse.py -v` 通过 9 个测试。
- 2026-06-12：完成 Task 4。Worker 子 agent 创建 `src/maildrop/security.py`、`src/maildrop/repository.py`、`tests/maildrop/test_repository.py`。组合验证 `.venv/bin/python -m pytest tests/maildrop/test_config.py tests/maildrop/test_models.py tests/maildrop/test_mailparse.py tests/maildrop/test_repository.py -v` 通过 15 个测试。
- 2026-06-12：完成 Task 5。Worker 子 agent 创建 `src/maildrop/app.py`、`src/maildrop/schemas.py`、`tests/maildrop/test_api.py`。验证 `.venv/bin/python -m pytest tests/maildrop -v` 通过 21 个测试。确认当前不定义全局 `app`，后续 Docker 需用 factory 启动。
- 2026-06-12：完成 Task 6。新增中文后台模板、样式和 `tests/maildrop/test_admin.py`，后台使用 Basic Auth、HMAC CSRF cookie、搜索分页和批量生成。修复 Secure CSRF cookie 在测试客户端 HTTP base URL 下不回传的问题，将 `client_with_db()` 调整为 `base_url="https://testserver"`，与生产 HTTPS 配置一致。验证 `.venv/bin/python -m pytest tests/maildrop/test_admin.py -v` 通过 8 个测试，`.venv/bin/python -m pytest tests/maildrop -v` 通过 29 个测试。
- 2026-06-12：推进 Task 7。创建 `.env.maildrop.example`、`Dockerfile`、`docker-compose.maildrop.yml`，更新 `README.md` 为 Maildrop 优先并保留 EmailEngine 历史/回滚说明；补充 `pyproject.toml` 的 package data，确保 Docker `pip install .` 后包含后台模板和 CSS。验证 `.venv/bin/python -m pytest tests/maildrop -v` 通过 29 个测试；用 Ruby 静态校验 Compose YAML、Dockerfile factory 启动和 package data 配置通过。本地无法执行 `docker compose config/build`，原因是当前环境没有 `docker` 命令。
- 2026-06-12：推进 Task 8/9。根据审查 agent 反馈修正 Postfix 生产风险：ingest 脚本按 HTTP 状态显式判定，2xx 才成功，其余统一 `exit 75`；`/etc/mail-api-ingest.env` 安装为 `root:mailapi 0640`；使用逐行 `postconf -e` 和 `postconf -M -e` 幂等安装；catch-all regexp 改为常量 `catchall`；加入 `mailapi_destination_recipient_limit = 1`；新增 `MAX_MESSAGE_BYTES` 配置并让应用默认读取该值。创建 `deploy/caddy/Caddyfile.maildrop` 并更新根 `Caddyfile`，屏蔽 `/internal/*`、反代到 `127.0.0.1:8000`。验证 `.venv/bin/python -m pytest tests/maildrop -v` 通过 31 个测试；`sh -n deploy/postfix/mail-api-ingest` 通过；Ruby 静态校验 Postfix/Caddy/Docker 配置通过。本地无 `docker`、`caddy` 命令，真实 build/validate 需在服务器执行。
- 2026-06-12：服务器部署完成主体。使用 SSH alias `emailengine` 连接服务器；同步项目到 `/opt/maildrop`；生成服务器 `.env.maildrop`；`docker compose -f docker-compose.maildrop.yml up -d --build` 成功，`app` 和 `postgres` 均 healthy；`curl http://127.0.0.1:8000/api/health` 返回 `{"success":true}`；后台本机 Basic Auth 验证通过。安装并配置 Postfix，25 端口监听，`postfix check` 无输出，`postmap -q probe@aiprot.space regexp:/etc/postfix/virtual_mailbox_regexp` 返回 `catchall`，`runuser -u mailapi` token 权限 smoke test 通过。本机 SMTP 测试投递到未知前缀，Postfix 日志显示 `status=sent (delivered via mailapi service)`，数据库 `unassigned_messages` 记录 `smtp-1781206700@aiprot.space|SMTP Smoke|alias_not_registered`。创建已登记 alias `reg1781207190@aiprot.space` 并通过 `/api/inbox/{prefix}/latest.txt?token=...` 读到 `Registered Smoke` / `Registered body`。Caddy 已验证并 reload，`https://aiprot.space/api/health` 正常，`https://aiprot.space/internal/ingest` 返回 404，`https://aiprot.space/admin` 未认证返回 401，带管理员密码可访问。EmailEngine/Redis 容器已 stop，未删除卷。
- 2026-06-12：DNS 检查结果：`aiprot.space A` 已为 `167.71.29.22`；`mail.aiprot.space A` 为空；`aiprot.space MX` 仍为 `0 mx1.efwd.spaceship.net.` 和 `0 mx2.efwd.spaceship.net.`；根 TXT 仍为 Spaceship SPF；`_dmarc.aiprot.space` 为空。Cloudflare API 查询当前账号没有 `aiprot.space` zone，因此 DNS 需要在当前 DNS 提供商/Spaceship 后台手动切换。
- 2026-06-12：新增 `scripts/maildrop-production-check.sh` 作为 DNS 切换后的重复验收脚本。验证 `sh -n scripts/maildrop-production-check.sh` 通过，Ruby 静态检查通过，`.venv/bin/python -m pytest tests/maildrop -q` 通过 32 个测试。实际运行 `scripts/maildrop-production-check.sh aiprot.space emailengine 167.71.29.22` 返回 exit `2`：HTTPS health、`/internal/*` 404、后台 401、Docker healthy、Postfix active、25 端口监听、Maildrop 绑定 `127.0.0.1:8000` 全部通过；DNS 四项仍未就绪：`mail.aiprot.space A` 为空，MX 仍为 Spaceship，SPF 仍为 Spaceship include，DMARC 为空。
- 2026-06-12：根据审查 agent 反馈加固生产验收脚本。新增 `tests/maildrop/test_production_check_script.py`，覆盖 DNS/service ready、旧 MX 残留、Docker `unhealthy` 三种场景；修复脚本 DNS 判断为精确 A/MX 集合匹配，DMARC 按 tag 检查根策略 `p=reject`，Docker health 用 Python 解析 JSON 行并要求 `app`、`postgres` 同时 `healthy/running`；增加 Postfix `virtual_transport`、`mailapi_destination_recipient_limit`、catch-all regexp、`mailapi` token 可读性和 DNS ready 后公网 SMTP 25 连接检查。修复 SSH 引号问题，确保 `INGEST_TOKEN` 在 `mailapi` shell 内展开。验证 `.venv/bin/python -m pytest tests/maildrop -q` 通过 35 个测试；真实运行 `scripts/maildrop-production-check.sh aiprot.space emailengine 167.71.29.22` 仍返回 exit `2`，所有服务检查 PASS，仅 DNS 四项 WARN。
- 2026-06-12：实现保留期/自动清理策略。新增 `MESSAGE_RETENTION_DAYS`、`UNASSIGNED_RETENTION_DAYS` 配置；新增 `cleanup_old_messages(..., dry_run=False)`，按 UTC aware cutoff 严格删除早于 cutoff 的 `messages` 和 `unassigned_messages`，等于 cutoff 保留；清理后重算受影响 alias 的 `message_count` 和 `last_message_at`，删光时归零/置空；新增 CLI `python -m maildrop.cli cleanup --dry-run` / `cleanup`，不导入 FastAPI app、不在应用启动执行。新增 `tests/maildrop/test_cli.py` 和清理边界测试，覆盖 dry-run、cutoff 边界、alias 统计归零。验证 `.venv/bin/python -m pytest tests/maildrop -q` 通过 41 个测试。
- 2026-06-12：部署保留期/清理策略到服务器。同步代码到 `/opt/maildrop`，补充服务器 `.env.maildrop` 中 `MESSAGE_RETENTION_DAYS=180` 和 `UNASSIGNED_RETENTION_DAYS=30`，重建 `maildrop-app` 镜像并启动成功，`app`/`postgres` 均 healthy。执行 `docker compose -f docker-compose.maildrop.yml exec -T app python -m maildrop.cli cleanup --dry-run` 返回 `{"aliases_updated": 0, "messages_deleted": 0, "unassigned_deleted": 0}`；安装 `/etc/cron.d/maildrop-cleanup`，使用 `flock -n /var/lock/maildrop-cleanup.lock` 防重入，手动执行正式 cleanup 返回同样 0 删除。验证 `.venv/bin/python -m pytest tests/maildrop -q` 通过 41 个测试；`scripts/maildrop-production-check.sh aiprot.space emailengine 167.71.29.22` 仍返回 exit `2`，所有服务检查 PASS，仅 DNS 四项 WARN；cron 文件存在且包含 `flock`。
- 2026-06-12：新增 DNS 切换后的真实公网收信验收脚本 `scripts/maildrop-public-smoke.py`。脚本先运行 `scripts/maildrop-production-check.sh`，只有 exit `0` 才继续；随后通过 `mail.aiprot.space:25` 发送唯一 `public-smoke-...@aiprot.space` 邮件，并通过 SSH 查询 PostgreSQL 的 `unassigned_messages` 确认投递。新增 `tests/maildrop/test_public_smoke_script.py` 覆盖 DNS 未就绪跳过、SMTP 发送和数据库确认、查询命令构造。验证 `.venv/bin/python -m pytest tests/maildrop -q` 通过 44 个测试。当时 DNS 未切换，因此该脚本会先跳过公网投递。
- 2026-06-12：再次复核 DNS 和生产状态。`scripts/maildrop-production-check.sh aiprot.space emailengine 167.71.29.22` 返回 exit `2`，所有服务项 PASS，仅 DNS 四项 WARN。本地 `.venv/bin/python -m pytest tests/maildrop -q` 通过 44 个测试。权威 DNS/托管方证据：`NS aiprot.space` 为 `launch1.spaceship.net.`、`launch2.spaceship.net.`；`SOA` 联系人为 `support.spaceship.com.`；`aiprot.space A` 为 `167.71.29.22`；`mail.aiprot.space A` 为空；MX 仍为 Spaceship efwd；SPF 仍 include Spaceship；DMARC 为空。当前无法通过本机或已连接 Cloudflare API 修改该 zone，必须在 Spaceship/DNS 后台完成 MX/TXT/A 记录切换后才能做真实公网收信最终验收。
- 2026-06-12：用户在 Spaceship 移除 `Email Forwarding Free` 默认记录后完成 DNS 切换。运行 `scripts/maildrop-production-check.sh aiprot.space emailengine 167.71.29.22` 返回 exit `0`：`mail.aiprot.space A -> 167.71.29.22`、`aiprot.space MX -> 10 mail.aiprot.space.`、SPF receive-only、DMARC reject、HTTPS health、公网 `/internal/*` 屏蔽、后台 401、Docker healthy、Postfix active、mailapi transport/catch-all/token、SMTP 25、公网 SMTP 连接全部 PASS。随后运行 `scripts/maildrop-public-smoke.py aiprot.space emailengine 167.71.29.22` 返回 exit `0`，公网 SMTP 测试邮件 `public-smoke-1781233657-91a5a0d5@aiprot.space` 已确认进入 `unassigned_messages`。
- 2026-06-12：根据多 agent 审计继续补齐落地缺口。新增后台 token 轮换能力：`POST /admin/aliases/{prefix}/token` 使用 Basic Auth + CSRF，重新生成 token hash，新 API 链接只在轮换结果页显示一次，旧 token 立即 403；新增回归测试覆盖旧 token 失效和新 token 可访问。Dockerfile 增加 Uvicorn `--no-access-log`，避免公开 API query token 写入应用访问日志，并新增静态测试防止回归。补充 1000+ 管理能力测试，覆盖 alias 大列表分页、搜索分页、未登记邮件分页和单 alias 邮件分页。更新 README/计划文件，修正 `/opt/emailengine` 到 `/opt/maildrop` 的 Maildrop 部署路径，并把 README 从“迁移草案”改为当前生产已切换状态。
- 2026-06-12：部署 token 轮换和 `--no-access-log` 到服务器 `/opt/maildrop`。使用 rsync 同步代码后执行 `docker compose -f docker-compose.maildrop.yml up -d --build app`，`maildrop-app-1` 重新构建并 healthy；`docker inspect maildrop-app-1 --format '{{json .Config.Cmd}}'` 确认启动命令包含 `--no-access-log`。本地 `.venv/bin/python -m pytest tests/maildrop -q` 通过 50 个测试，`git diff --check` 通过；生产 `scripts/maildrop-production-check.sh aiprot.space emailengine 167.71.29.22` 返回 exit `0`；公网 smoke `scripts/maildrop-public-smoke.py aiprot.space emailengine 167.71.29.22` 返回 exit `0`，测试邮件 `public-smoke-1781235189-308aaa04@aiprot.space` 已确认进入 `unassigned_messages`。
- 2026-06-12：提交前再次运行 `.venv/bin/python -m pytest tests/maildrop -q` 通过 50 个测试，`git diff --check` 通过，`scripts/maildrop-production-check.sh aiprot.space emailengine 167.71.29.22` 返回 exit `0`，`scripts/maildrop-public-smoke.py aiprot.space emailengine 167.71.29.22` 返回 exit `0`，测试邮件 `public-smoke-1781235189-308aaa04@aiprot.space` 已确认进入 `unassigned_messages`。检查 `.gitignore` 确认 `.env`、`.env.maildrop`、`.venv`、pytest/cache 和 pyc 均被忽略；可提交 env example 文件只包含占位值。
- 2026-06-12：创建统一初始提交 `feat: deploy maildrop receive-only service`，覆盖 Maildrop 应用、测试、部署、运维文档、生产验收脚本、EmailEngine 历史回滚文件和主状态文件。提交前已替换计划文件中残留的真实 Basic Auth 示例为 `<ADMIN_PASSWORD>` 占位符。
- 2026-06-12：根据用户新增需求开始实现“导出已有邮箱及 API 链接”。确认当前系统不保存明文 token，因此采用“导出并轮换 token”方案。新增计划文件 `docs/superpowers/plans/2026-06-12-maildrop-export-links.md`；按 TDD 增加后台测试，覆盖导出选中 alias 只轮换选中项、导出全部 alias 轮换全部 token、未选择时返回 400。实现 `POST /admin/aliases/export`，返回 `maildrop-alias-links.txt` 文本附件，每行格式为 `email https://aiprot.space/api/inbox/{prefix}/latest.txt?token=...`；后台列表新增复选框、当前页全选、`导出选中并轮换 token`、`导出全部并轮换 token`。本地 `.venv/bin/python -m pytest tests/maildrop -q` 通过 53 个测试。
- 2026-06-12：导出功能已部署到服务器 `/opt/maildrop` 并完成生产验收。针对本地 UDP DNS 到 `1.1.1.1` 超时导致验收误报的问题，生产检查脚本新增 DNS TCP 回退并补充回归测试；本地 `.venv/bin/python -m pytest tests/maildrop -q` 通过 54 个测试，`scripts/maildrop-production-check.sh aiprot.space emailengine 167.71.29.22` 返回 exit `0`，`scripts/maildrop-public-smoke.py aiprot.space emailengine 167.71.29.22` 返回 exit `0`，测试邮件 `public-smoke-1781239240-2764ab6b@aiprot.space` 已确认进入 `unassigned_messages`。
- 2026-06-12：根据用户新增需求实现并部署 alias 分类和软删除。已确认删除语义为软删除、保留历史邮件、暂不做恢复按钮；新增设计规格 `docs/superpowers/specs/2026-06-12-maildrop-alias-categories-delete-design.md` 和实施计划 `docs/superpowers/plans/2026-06-12-maildrop-alias-categories-delete.md`。实现 Alembic 基础配置、`exported_at`/`deleted_at` nullable 迁移、导出状态记录、分类过滤、单个/批量软删除、删除后收信进入未登记邮件 `alias_deleted`。修复 Dockerfile 未复制 Alembic 文件导致容器内迁移失败的问题，并为生产检查/公网 smoke 增加服务器侧 SMTP fallback。本地 `.venv/bin/python -m pytest tests/maildrop -q` 通过 64 个测试；服务器已 `docker compose build app`、`alembic upgrade head`、重启 app 并 healthy；`scripts/maildrop-production-check.sh aiprot.space emailengine 167.71.29.22` 返回 exit `0`，`scripts/maildrop-public-smoke.py aiprot.space emailengine 167.71.29.22` 返回 exit `0`，测试邮件 `public-smoke-1781258315-4d3046ac@aiprot.space` 已确认进入 `unassigned_messages`；生产 HTTPS 后台软删除 smoke 创建并删除 `deletesmoke1781258395@aiprot.space`，确认 `deleted=True`、`enabled=False`。

## 下次推进检查清单

每次继续前检查：

- 阅读本文件。
- 阅读当前计划任务。
- 查看 `git status --short --branch`。
- 确认没有覆盖用户未请求的改动。
- 每完成一个计划任务，更新本文件的“当前状态”和“执行记录”。

## 生产门禁状态

- 已满足：第一版明确为全新部署；生产 schema 变更前必须补 Alembic。
- 已满足：Caddy 对 `/internal/*` 返回 404，应用端仍校验 ingest token 和来源。
- 已满足：Postfix transport 幂等安装，pipe 失败返回临时错误码 75。
- 已满足：PostgreSQL 备份和恢复命令已写入 `docs/maildrop-ops.md`。
- 已满足：应用健康检查覆盖数据库连通性。
- 已满足：单次邮件大小限制由 `MAX_MESSAGE_BYTES` 与 Postfix `message_size_limit` 同步控制。
- 已满足：DNS MX/TXT 已从 Spaceship Email Forwarding Free 切到自建 Maildrop，并通过公网真实 SMTP smoke 验收。
- 已满足：未登记邮件/原始邮件的长期保留期和自动清理策略已实现，生产 cron 需使用 `flock` 并先 dry-run。
- 已满足：公开 API query token 泄漏风险已降低，生产 Uvicorn access log 已关闭，后台支持 token 轮换。
- 已满足：后台导出邮箱和 API 链接功能已部署并通过生产验收；导出会轮换相关 alias 的 token。
- 已满足：后台 alias 分类和软删除功能已部署并通过生产验收；涉及 schema 变更的部署已通过 Alembic 管理。
