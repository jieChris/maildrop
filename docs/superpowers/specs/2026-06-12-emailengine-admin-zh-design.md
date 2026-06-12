# EmailEngine 管理后台汉化设计

目标：在当前私有部署中汉化 EmailEngine 管理后台，保持官方 Docker 镜像可升级，避免直接修改容器内文件。

方案：采用覆盖文件挂载。把需要覆盖的模板和静态资源放在本地 `overrides/emailengine/`，通过 `docker-compose.yml` 只读挂载到容器对应路径。第一版优先覆盖后台全局布局，注入本地 `admin-zh.js`，用词典和 DOM MutationObserver 翻译导航、按钮、表单、提示、表格标题、页面标题等后台可见英文；保留模板覆盖能力，后续可逐页做无闪烁的原生模板汉化。

范围：管理后台 `/admin` 下的 Dashboard、Email Accounts、Access Tokens、Webhooks、Gateways、Templates、Settings、OAuth2、License、Security 等主要页面。Swagger/API 文档、第三方依赖界面、日志中的英文不作为第一版范围。

部署：新增 `overrides/emailengine/static/js/admin-zh.js` 和覆盖后的 `overrides/emailengine/views/layout/app.hbs`。Compose 挂载这些文件后重建 EmailEngine 容器。

验证：确认 `docker compose ps` 为 healthy，`/health` 返回成功，公网 HTTPS 可访问，并抓取后台 HTML 确认汉化脚本已加载。
