# Spaceship DNS 配置指南

本文说明如何在 Spaceship 把域名解析到 Maildrop。示例使用：

- 域名：`example.com`
- 服务器 IP：`203.0.113.10`
- 邮件入口主机：`mail.example.com`

把示例值替换成你的真实域名和服务器 IP。

## 前置检查

进入 Spaceship：

1. 打开 `Domain List`
2. 选择你的域名
3. 打开 `Advanced DNS`
4. 确认名称服务器使用 Spaceship nameserver

如果域名使用 Cloudflare 或其他 DNS 服务商，这份记录仍然适用，但需要在实际 DNS 服务商处添加。

## 必须删除或关闭的记录

如果你开过 Spaceship 的 `Email Forwarding Free`，需要移除它自动创建的邮件转发记录，否则会和自建 Maildrop 冲突。

删除或禁用类似记录：

```text
@ MX 0 mx1.efwd.spaceship.net
@ MX 0 mx2.efwd.spaceship.net
@ TXT v=spf1 include:spf.efwd.spaceship.net ~all
```

如果界面提示 MX 冲突，不要同时保留 Spaceship 转发 MX 和 Maildrop MX。

## 根域收信记录

添加或确认这些记录：

```text
主机: mail
类型: A
值: 203.0.113.10
TTL: 默认或 20/30 分钟

主机: @
类型: MX
值: mail.example.com.
优先级: 10
TTL: 默认或 20/30 分钟

主机: @
类型: TXT
值: v=spf1 -all
TTL: 默认或 20/30 分钟

主机: _dmarc
类型: TXT
值: v=DMARC1; p=reject; sp=reject; adkim=s; aspf=s
TTL: 默认或 20/30 分钟
```

注意：

- MX 的值建议写成 `mail.example.com.`，最后有一个点。
- Maildrop 默认只收信不发信，所以 SPF 用 `v=spf1 -all`。
- 如果未来这个域名还要发信，需要改成发信服务商提供的 SPF/DKIM/DMARC。

## 常用子域名收信

如果要让 `ssn.example.com`、`sso.example.com` 这类固定子域名也能收信，每个子域名添加：

```text
主机: ssn
类型: MX
值: mail.example.com.
优先级: 10

主机: ssn
类型: TXT
值: v=spf1 -all
```

然后在服务器 `.env.maildrop` 的 `MAIL_DOMAINS` 中加入完整域名：

```dotenv
MAIL_DOMAINS=example.com,ssn.example.com,sso.example.com
```

## 登记式通配子域名

如果要支持后台登记式子域名，例如：

```text
a.exa.example.com
b.exa.example.com
c.exa.example.com
exe.example.com
c.exe.example.com
```

在 Spaceship 添加：

```text
主机: *.exa
类型: MX
值: mail.example.com.
优先级: 10

主机: *.exa
类型: TXT
值: v=spf1 -all

主机: exa
类型: MX
值: mail.example.com.
优先级: 10

主机: exa
类型: TXT
值: v=spf1 -all
```

说明：

- `*.exa.example.com` 覆盖 `a.exa.example.com`、`b.exa.example.com` 等单级/多级查询的 DNS 响应，实际是否可用由 Maildrop 后台登记控制。
- `exa.example.com` 本身不是 `*.exa.example.com`，所以需要单独添加 `exa` 的 MX/TXT。
- Maildrop 后台 `/admin/subdomains` 新增 `c` 后，才会允许生成 `@c.exa.example.com` 邮箱。

后台也可以登记其他主域下的邮箱后缀：

- 输入 `exe.example.com`，新增 `@exe.example.com` 邮箱后缀。
- 输入 `c.exe`，新增 `@c.exe.example.com` 邮箱后缀。
- 输入 `c` 仍按兼容规则新增 `@c.exa.example.com` 邮箱后缀。

如果要让 `exe.example.com` 或 `c.exe.example.com` 真正收到外部邮件，DNS 也要有对应 MX：

```text
主机: exe
类型: MX
值: mail.example.com.
优先级: 10

主机: exe
类型: TXT
值: v=spf1 -all

主机: *.exe
类型: MX
值: mail.example.com.
优先级: 10

主机: *.exe
类型: TXT
值: v=spf1 -all
```

如果某个具体主机名已经有 TXT 验证记录，例如 `abc.exe TXT openai-domain-verification=...`，
通配 MX 可能不会覆盖它。此时需要给 `abc.exe` 单独补一条 MX。

## DNS 验证命令

在本地或服务器运行：

```bash
dig +short A mail.example.com @1.1.1.1
dig +short MX example.com @1.1.1.1
dig +short TXT example.com @1.1.1.1
dig +short TXT _dmarc.example.com @1.1.1.1
dig +short MX a.exa.example.com @1.1.1.1
dig +short TXT a.exa.example.com @1.1.1.1
```

期望类似：

```text
203.0.113.10
10 mail.example.com.
"v=spf1 -all"
"v=DMARC1; p=reject; sp=reject; adkim=s; aspf=s"
10 mail.example.com.
"v=spf1 -all"
```

## 常见问题

### 后台能访问，但收不到外部邮件

检查：

- MX 是否还指向 Spaceship Email Forwarding。
- `mail.example.com` A 是否指向服务器公网 IP。
- 云服务器防火墙是否开放 TCP 25、80、443。
- 云服务商是否默认封锁入站或出站 25。
- Postfix 是否正在运行：`systemctl status postfix`。

### `a.exa.example.com` 能查到 MX，但后台没有这个后缀

DNS 只负责把邮件送到服务器。还需要在 Maildrop 后台：

```text
/admin/subdomains
```

新增 `a`，后台生成邮箱时才会出现 `a.exa.example.com`。

### `@exa.example.com` 收不到

`exa.example.com` 不是通配记录覆盖范围，需要单独添加 `exa` 的 MX/TXT，并且在应用配置中加入 `exa.example.com`。

## 通过 Spaceship API 自动登记 OpenAI TXT 子域名

如果你会在 Spaceship 中添加类似记录：

```text
主机: urxg.exa
类型: TXT
值: openai-domain-verification=xxxx
```

可以让 Maildrop 后台读取 Spaceship DNS 记录，并自动把
`urxg.exa.example.com` 登记为可生成邮箱的子域名。

### API 权限

Spaceship API Key 只需要读取权限：

```text
domains:read
dnsrecords:read
```

不要给 `dnsrecords:write`，除非你明确要让系统以后自动修改 DNS。
当前同步功能只读取 TXT 记录，不会创建、修改或删除 Spaceship DNS 记录。

### 环境变量

在服务器 `.env.maildrop` 中配置以下四项；它们都需要显式填写，同步功能才会启用：

```dotenv
SPACESHIP_API_KEY=你的只读 API Key
SPACESHIP_API_SECRET=你的只读 API Secret
SPACESHIP_DNS_DOMAIN=example.com
SPACESHIP_AUTO_REGISTER_TXT_PREFIX=openai-domain-verification=
```

修改后重启 app：

```bash
cd /opt/maildrop
docker compose -f docker-compose.maildrop.yml up -d app
```

### 后台同步

打开：

```text
https://example.com/admin/subdomains
```

点击：

```text
从 Spaceship TXT 记录同步
```

系统会读取 `example.com` 的 DNS 记录，匹配：

- 类型是 `TXT`
- 主机名属于 `*.exa.example.com`
- TXT 值以 `openai-domain-verification=` 开头
- 当前还没有登记到 Maildrop

匹配成功后会自动新增到子域名管理列表，批量生成邮箱的后缀下拉也会出现对应后缀。
