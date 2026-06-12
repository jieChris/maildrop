(function () {
    'use strict';

    const exact = new Map(Object.entries({
        'Dashboard': '仪表盘',
        'System': '系统',
        'Email Accounts': '邮箱账户',
        'Email Gateways': '邮件网关',
        'Email Templates': '邮件模板',
        'Webhook Routing': 'Webhook 路由',
        'Tools': '工具',
        'Accounts': '账户',
        'Accounts total': '账户总数',
        'Accounts active': '活跃账户',
        'Access Tokens': '访问令牌',
        'Webhooks': 'Webhook',
        'Gateways': '网关',
        'Templates': '模板',
        'Settings': '设置',
        'General Settings': '常规设置',
        'System Configuration': '系统配置',
        'Service': '服务',
        'SMTP': 'SMTP',
        'SMTP Interface': 'SMTP 接口',
        'IMAP Proxy': 'IMAP 代理',
        'AI Processing': 'AI 处理',
        'Document Store': '文档存储',
        'Logging': '日志',
        'Network': '网络',
        'Language': '语言',
        'Default Language': '默认语言',
        'Timezone': '时区',
        'License': '许可证',
        'License and terms': '许可证和条款',
        'OAuth2': 'OAuth2',
        'OAuth2 Applications': 'OAuth2 应用',
        'Account security': '账户安全',
        'Sign out': '退出登录',
        'Search': '搜索',
        'All': '全部',
        'Create': '创建',
        'Add': '添加',
        'Edit': '编辑',
        'Delete': '删除',
        'Remove': '移除',
        'Save': '保存',
        'Update': '更新',
        'Cancel': '取消',
        'Close': '关闭',
        'Continue': '继续',
        'Back': '返回',
        'Go back': '返回',
        'Submit': '提交',
        'Reset': '重置',
        'Enable': '启用',
        'Disable': '禁用',
        'Enabled': '已启用',
        'Disabled': '已禁用',
        'enabled': '已启用',
        'disabled': '已禁用',
        'Active': '活跃',
        'Inactive': '未活跃',
        'Connected': '已连接',
        'Disconnected': '已断开',
        'Failed': '失败',
        'Pending': '待处理',
        'State': '状态',
        'Status': '状态',
        'Name': '名称',
        'Description': '描述',
        'Email address': '邮箱地址',
        'Password': '密码',
        'Username': '用户名',
        'Hostname': '主机名',
        'Port': '端口',
        'Security': '安全',
        'TLS': 'TLS',
        'Created': '创建时间',
        'Updated': '更新时间',
        'Actions': '操作',
        'Details': '详情',
        'Overview': '概览',
        'Configuration': '配置',
        'Advanced': '高级',
        'Test': '测试',
        'Send': '发送',
        'Sending': '发送中',
        'Messages': '邮件',
        'Message': '邮件',
        'Mailbox': '邮箱文件夹',
        'Mailboxes': '邮箱文件夹',
        'Path': '路径',
        'Subject': '主题',
        'From': '发件人',
        'To': '收件人',
        'Cc': '抄送',
        'Bcc': '密送',
        'Reply-To': '回复到',
        'Preview': '预览',
        'Content': '内容',
        'Headers': '邮件头',
        'Attachments': '附件',
        'Download': '下载',
        'Upload': '上传',
        'Import': '导入',
        'Export': '导出',
        'API': 'API',
        'API Reference': 'API 参考',
        'API authentication': 'API 认证',
        'Require API Authentication': '要求 API 认证',
        'Allow OAuth2 Token Access via API': '允许通过 API 访问 OAuth2 令牌',
        'Public Interface': '公共界面',
        'Public URL': '公共 URL',
        'Service URL': '服务 URL',
        'Service Secret': '服务密钥',
        'Behind Reverse Proxy': '位于反向代理后',
        'Data Encryption': '数据加密',
        'Admin IP Restrictions': '管理员 IP 限制',
        'Allow Insecure Email Certificates': '允许不安全的邮件证书',
        'Queue Management': '队列管理',
        'Job History Limit': '任务历史保留数',
        'Email Delivery': '邮件投递',
        'Retry Attempts': '重试次数',
        'IMAP Processing': 'IMAP 处理',
        'Indexing Method': '索引方式',
        'Export Settings': '导出设置',
        'Gmail Export Batch Size': 'Gmail 导出批大小',
        'Outlook Export Batch Size': 'Outlook 导出批大小',
        'Public Page Customization': '公共页面自定义',
        'Brand Name': '品牌名称',
        'Page Header HTML': '页面头部 HTML',
        'Header template': '头部模板',
        'Custom <head> HTML': '自定义 <head> HTML',
        'Head content': 'Head 内容',
        'Webhook Scripts': 'Webhook 脚本',
        'Script Variables (JSON)': '脚本变量 (JSON)',
        'Global variables': '全局变量',
        'Email Tracking': '邮件追踪',
        'Track Link Clicks': '追踪链接点击',
        'Track Email Opens': '追踪邮件打开',
        'Gmail Features': 'Gmail 功能',
        'Detect Gmail Categories (IMAP)': '检测 Gmail 分类 (IMAP)',
        'Save Changes': '保存更改',
        'Toggle fullscreen': '切换全屏',
        'How to override': '如何覆盖',
        'Help us translate EmailEngine': '帮助我们翻译 EmailEngine',
        'Proxy': '代理',
        'Webhook URL': 'Webhook URL',
        'Events': '事件',
        'Event': '事件',
        'Queue': '队列',
        'Webhooks queue': 'Webhook 队列',
        'Submission queue': '提交队列',
        'Software versions': '软件版本',
        'Redis Latency': 'Redis 延迟',
        'New emails': '新邮件',
        'Webhooks sent': '已发送 Webhook',
        'Webhooks failed': '失败的 Webhook',
        'Emails sent': '已发送邮件',
        'Emails rejected': '被拒邮件',
        'Successful API calls': '成功 API 调用',
        'Failed API calls': '失败 API 调用',
        'License key missing': '缺少许可证密钥',
        'Register a license': '注册许可证',
        'Start a 14-day trial': '开始 14 天试用',
        'Authentication not enabled': '未启用身份认证',
        'Enable authentication': '启用身份认证',
        'System notifications': '系统通知',
        'Something went wrong': '出现错误',
        'Error code: %s': '错误代码：%s',
        'No accounts found': '未找到账户',
        'No accounts found.': '未找到账户。',
        'Add account': '添加账户',
        'Add an account': '添加账户',
        'New account': '新建账户',
        'Edit account': '编辑账户',
        'Delete account': '删除账户',
        'Register account': '注册账户',
        'Your name': '你的姓名',
        'Enter your full name': '输入你的完整姓名',
        'Enter your email address': '输入你的邮箱地址',
        'Enter your account password': '输入你的账户密码',
        'New token': '新建令牌',
        'Token': '令牌',
        'Scopes': '权限范围',
        'New webhook': '新建 Webhook',
        'Edit webhook': '编辑 Webhook',
        'New gateway': '新建网关',
        'Edit gateway': '编辑网关',
        'New template': '新建模板',
        'Edit template': '编辑模板',
        'OAuth2 Apps': 'OAuth2 应用',
        'New OAuth2 App': '新建 OAuth2 应用',
        'Edit OAuth2 App': '编辑 OAuth2 应用',
        'Client ID': '客户端 ID',
        'Client Secret': '客户端密钥',
        'Redirect URL': '重定向 URL',
        'Authority': '授权机构',
        'Tenant': '租户',
        'Application ID': '应用 ID',
        'Application secret': '应用密钥',
        'Copy': '复制',
        'Copied': '已复制',
        'Success': '成功',
        'Error': '错误',
        'Warning': '警告',
        'Info': '信息',
        'OK': '确定',
        'OK?': '确定？',
        'Search for accounts…': '搜索账户…'
    }));

    const replacements = [
        [/EmailEngine – Dashboard/g, 'EmailEngine - 仪表盘'],
        [/EmailEngine - Dashboard/g, 'EmailEngine - 仪表盘'],
        [/EmailEngine – Email Accounts/g, 'EmailEngine - 邮箱账户'],
        [/EmailEngine - Email Accounts/g, 'EmailEngine - 邮箱账户'],
        [/EmailEngine – General Settings/g, 'EmailEngine - 常规设置'],
        [/EmailEngine - General Settings/g, 'EmailEngine - 常规设置'],
        [/Welcome to EmailEngine!/g, '欢迎使用 EmailEngine！'],
        [/Get started by connecting your first email account\. Once connected, you can send and receive emails through the/g, '先连接第一个邮箱账户。连接后，你就可以通过'],
        [/You can also add accounts programmatically via the/g, '你也可以通过'],
        [/API endpoint/g, 'API 端点'],
        [/Get started by connecting your first email account\. Once connected, you can send and receive emails through the API\./g, '先连接第一个邮箱账户。连接后，你就可以通过 API 收发邮件。'],
        [/You can also add accounts programmatically via the API endpoint\./g, '你也可以通过 API 端点以编程方式添加账户。'],
        [/Connect your first account/g, '连接第一个账户'],
        [/Email Gateways/g, '邮件网关'],
        [/Email Templates/g, '邮件模板'],
        [/Webhook Routing/g, 'Webhook 路由'],
        [/Software versions/g, '软件版本'],
        [/Submission queue/g, '提交队列'],
        [/Redis Latency/g, 'Redis 延迟'],
        [/New emails/g, '新邮件'],
        [/Webhooks sent/g, '已发送 Webhook'],
        [/Webhooks failed/g, '失败的 Webhook'],
        [/Emails sent/g, '已发送邮件'],
        [/Emails rejected/g, '被拒邮件'],
        [/Successful API calls/g, '成功 API 调用'],
        [/Failed API calls/g, '失败 API 调用'],
        [/EmailEngine is currently not syncing any accounts\. Please restart the application or register a valid license key to enable syncing\./g, 'EmailEngine 当前未同步任何账户。请重启应用或注册有效许可证密钥以启用同步。'],
        [/To use all the features of EmailEngine, you need to provide a valid license key\./g, '要使用 EmailEngine 的全部功能，需要提供有效的许可证密钥。'],
        [/To enable authentication for EmailEngine, please set a password for the admin user account\./g, '要为 EmailEngine 启用身份认证，请为管理员账户设置密码。'],
        [/EmailEngine is currently not running and does not process any email accounts/g, 'EmailEngine 当前未运行，也不会处理任何邮箱账户'],
        [/Engine is stopped/g, '引擎已停止'],
        [/Provisioning a trial license, please wait/g, '正在开通试用许可证，请稍候'],
        [/Request failed with status/g, '请求失败，状态码'],
        [/Request failed/g, '请求失败'],
        [/No active license/g, '没有有效许可证'],
        [/Running in limited mode/g, '正在以受限模式运行'],
        [/General settings for EmailEngine/g, 'EmailEngine 常规设置'],
        [/Settings updated/g, '设置已更新'],
        [/Account updated/g, '账户已更新'],
        [/Account deleted/g, '账户已删除'],
        [/Webhook updated/g, 'Webhook 已更新'],
        [/Webhook deleted/g, 'Webhook 已删除'],
        [/Token created/g, '令牌已创建'],
        [/Token deleted/g, '令牌已删除'],
        [/Are you sure\?/g, '确定要继续吗？'],
        [/This action can not be undone\./g, '此操作无法撤销。'],
        [/Show only Google Workspace accounts/g, '仅显示 Google Workspace 账户'],
        [/Accounts using service access can only be added via the API/g, '使用服务访问的账户只能通过 API 添加'],
        [/Accounts using application access can only be added via the hosted authentication form/g, '使用应用访问的账户只能通过托管认证表单添加'],
        [/Configure core settings for your EmailEngine instance\./g, '配置当前 EmailEngine 实例的核心设置。'],
        [/Base URL where EmailEngine is accessible \(without any path\)\./g, 'EmailEngine 可访问的基础 URL（不包含路径）。'],
        [/Enable if using Nginx, Caddy, or similar\. Uses/g, '如果使用 Nginx、Caddy 或类似反向代理，请启用。使用'],
        [/headers to identify client IPs\./g, '请求头识别客户端 IP。'],
        [/Default language for UI and API responses\./g, 'UI 和 API 响应的默认语言。'],
        [/HMAC key for signing public requests\. Changing this invalidates all existing tracking links\./g, '用于签名公开请求的 HMAC 密钥。修改后会使现有追踪链接失效。'],
        [/Disable for development only\. Always enable in production for secure API access\./g, '仅在开发环境禁用。生产环境应始终启用以保护 API 访问。'],
        [/environment variable at startup to enable\./g, '环境变量以启用。'],
        [/Learn more/g, '了解更多'],
        [/Accept self-signed or expired certificates for IMAP\/SMTP connections\. Not recommended\./g, '允许 IMAP/SMTP 连接使用自签名或过期证书。不推荐。'],
        [/Number of completed\/failed jobs to keep in/g, '要在'],
        [/Set to 0 to disable history\./g, '设为 0 可禁用历史记录。'],
        [/How many times to retry failed email deliveries\./g, '邮件投递失败后的重试次数。'],
        [/Configure batch sizes for bulk message export operations\./g, '配置批量邮件导出操作的批大小。'],
        [/Number of parallel requests when fetching Gmail messages for export/g, '导出 Gmail 邮件时的并行请求数量'],
        [/Messages per batch request for Outlook exports/g, 'Outlook 导出时每批请求的邮件数量'],
        [/Limited by Microsoft Graph API\./g, '受 Microsoft Graph API 限制。'],
        [/Customize public pages like authentication forms, error pages, and unsubscribe pages\./g, '自定义认证表单、错误页、退订页等公共页面。'],
        [/Appears in browser title bar/g, '显示在浏览器标题栏中'],
        [/HTML shown at the top of public pages/g, '显示在公共页面顶部的 HTML'],
        [/Add custom CSS, fonts, or analytics scripts/g, '添加自定义 CSS、字体或统计脚本'],
        [/Global settings for filter and map functions in/g, '过滤和映射函数的全局设置，适用于'],
        [/webhook routes/g, 'Webhook 路由'],
        [/JSON object available as/g, '可作为'],
        [/variable in all filter and map functions/g, '变量在所有过滤和映射函数中使用的 JSON 对象'],
        [/Use for shared secrets like API keys, access tokens, or configuration values\./g, '可用于共享 API 密钥、访问令牌或配置值等敏感信息。'],
        [/Rewrite links to track when recipients click them\./g, '重写链接以追踪收件人的点击。'],
        [/Add a tracking pixel to detect when emails are opened\./g, '添加追踪像素以检测邮件是否被打开。'],
        [/Important:/g, '重要：'],
        [/must be publicly accessible for tracking to work\./g, '必须可公网访问，追踪功能才能正常工作。'],
        [/See/g, '查看'],
        [/documentation/g, '文档'],
        [/for per-message overrides\./g, '了解单封邮件级别的覆盖设置。'],
        [/Identify which Gmail tab/g, '识别 Gmail 标签页'],
        [/new emails belong to\./g, '新邮件所属分类。'],
        [/Gmail API accounts get this automatically\./g, 'Gmail API 账户会自动获得此信息。']
    ];

    function normalize(value) {
        return String(value || '').replace(/\s+/g, ' ').trim();
    }

    function translateText(value) {
        const original = String(value || '');
        const key = normalize(original);

        if (!key) {
            return original;
        }

        let translated = exact.get(key) || key;
        for (const [pattern, replacement] of replacements) {
            translated = translated.replace(pattern, replacement);
        }

        if (translated === key) {
            return original;
        }

        const leading = original.match(/^\s*/)[0];
        const trailing = original.match(/\s*$/)[0];
        return `${leading}${translated}${trailing}`;
    }

    function translateElementAttributes(root) {
        const selector = [
            '[placeholder]',
            '[title]',
            '[aria-label]',
            '[data-original-title]',
            'input[type="button"][value]',
            'input[type="submit"][value]'
        ].join(',');

        root.querySelectorAll(selector).forEach(el => {
            ['placeholder', 'title', 'aria-label', 'data-original-title', 'value'].forEach(attr => {
                if (!el.hasAttribute || !el.hasAttribute(attr)) {
                    return;
                }

                const translated = translateText(el.getAttribute(attr));
                if (translated !== el.getAttribute(attr)) {
                    el.setAttribute(attr, translated);
                }
            });
        });
    }

    function translateTextNodes(root) {
        const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, {
            acceptNode(node) {
                const parent = node.parentElement;
                if (!parent || ['SCRIPT', 'STYLE', 'TEXTAREA', 'CODE', 'PRE'].includes(parent.tagName)) {
                    return NodeFilter.FILTER_REJECT;
                }

                return normalize(node.nodeValue) ? NodeFilter.FILTER_ACCEPT : NodeFilter.FILTER_REJECT;
            }
        });

        const nodes = [];
        while (walker.nextNode()) {
            nodes.push(walker.currentNode);
        }

        nodes.forEach(node => {
            const translated = translateText(node.nodeValue);
            if (translated !== node.nodeValue) {
                node.nodeValue = translated;
            }
        });
    }

    function translateDocument() {
        translateTextNodes(document.body || document.documentElement);
        translateElementAttributes(document);
        document.title = translateText(document.title).replace('EmailEngine - ', 'EmailEngine - ');
    }

    function start() {
        translateDocument();

        const observer = new MutationObserver(() => {
            window.clearTimeout(start.pending);
            start.pending = window.setTimeout(translateDocument, 50);
        });

        observer.observe(document.body || document.documentElement, {
            childList: true,
            subtree: true,
            characterData: true,
            attributes: true,
            attributeFilter: ['placeholder', 'title', 'aria-label', 'data-original-title', 'value']
        });
    }

    window.EmailEngineAdminZh = { translateText, translateDocument };

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', start);
    } else {
        start();
    }
})();
