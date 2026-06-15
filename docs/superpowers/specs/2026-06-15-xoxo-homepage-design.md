# XOXO 公开主页设计

## 目标

为 `xoxo.edu.kg` 的根路径 `/` 设计并实现一个公开大学主页，定位为
X-Order Xenotech Observatory（X秩序异构科技观测大学）的未来研究型大学门面。
现有 Maildrop 管理后台、收件管理器和公开 API 不改动：

- `/admin` 继续使用 Basic Auth 管理后台。
- `/xxxmailmanage` 继续作为收件管理器。
- `/api/*` 和 `/internal/*` 行为保持不变。

## 设计方向

采用“黑环观测台”方向。首页第一视觉必须来自 XOXO 校徽语言：黑色圆环、交叉双 X
轨道、深空信号、异常科技观测。页面整体要像一台正在运行的未来观测仪，同时仍是可读的大学官网。

视觉关键词：

- 深黑背景、银白文字、深紫/冷蓝能量雾、荧光绿色信号光。
- 大量圆角、轨道、胶囊和流体玻璃，减少直角线框。
- 动态深空粒子场、轨道粒子、信号流、扫描层。
- 元素 hover 必须有交互动画，包括发光、上浮、边缘扫光、轨道加速。

## 首屏结构

首屏顶部放大号学校名称，作为第一视觉锚点：

- `X-Order Xenotech Observatory`
- `X秩序异构科技观测大学`
- `xoxo.edu.kg`
- `The Observatory`

大校名使用未来终端式字体、发光呼吸、横向扫描和轻微信号感。它应比小 logo 和导航更显眼。

首屏主体包含：

- 校训：`Observe the Unknown. Order the Impossible.`
- 中文校训：`观测未知，重构不可能。`
- 简介：一所坐落于中亚零号谷的未来研究型大学，研究异常系统、深空信号、异源科技与人类文明延续。
- CTA：`Apply to the 404`、`Explore Six Schools`、`Open Observatory Network`
- 右侧或首屏核心区域展示动态校徽仪器：黑环、双 X 轨道、发光核心和 `X O X O` 字符。

## 页面内容

首页以单页滚动方式组织信息：

1. 顶部导航  
   胶囊式导航，包含 Academics、Signal Archive、Admissions、Null Valley。

2. 使命信息条  
   胶囊信息条展示 mission、signal、admission、location：
   `MISSION / 观测未知，重构不可能`、`SIGNAL / X-ORDER REPEATING`、
   `ADMISSION / 404 UNDERGRADUATES`、`LOCATION / KYRGYZ RESEARCH ZONE`。

3. 六大学院  
   使用圆角玻璃卡片展示六大学院，卡片上有微型轨道/信号装饰：
   Xenotech Engineering、X-Order Mathematics、Deep Signal Studies、Synthetic Life、
   Orbital Architecture、Human Continuity。

4. 校园四环区  
   用圆形动态环图表现校园是一台观测仪：
   O-Ring、X-Ring、Null Core、Horizon Field。每个区域配中文说明。

5. 招生与校园文化  
   展示每年 404 名本科生、异常问题解决能力、Midnight Observation、
   Broken Exam、No Map Week、XOXO Letters 等内容。

6. 底部入口  
   展示 Portal X、NullCore Access、X-Order Archive、核心邮箱地址。
   这些入口可作为视觉按钮，不需要连接真实业务系统。

## 背景粒子系统

背景不能只是静态星点。实现时使用 CSS 和少量 JavaScript：

- 深空粒子持续漂浮。
- 轨道粒子沿大椭圆路径运动。
- 竖向信号流以低透明度下落。
- 能量雾缓慢漂移。
- 扫描层周期性扫过页面。
- 鼠标移动时，背景光晕和部分粒子产生轻微视差响应。

应提供 `prefers-reduced-motion` 降级：减少动画时保留静态视觉，不影响阅读。

## 自定义鼠标

使用 A 方案：`X-Arrow` 未来切面指针。

要求：

- 不使用圆形准星作为主鼠标，避免不符合操作直觉。
- 保留传统箭头的指向性。
- 箭头使用荧光绿色描边、半透明填充和冷蓝信号尾迹。
- 悬停到按钮、导航、卡片、校徽、校园环图等元素时，光标增强发光并显示短尾迹。
- 移动端和减少动画环境下禁用自定义光标，回退系统默认行为。

## 技术实现

项目是 FastAPI + Jinja2 + 静态 CSS，无独立前端构建链。

计划新增：

- `GET /` 公开主页路由。
- `src/maildrop/templates/home.html` 独立模板，不继承后台 `base.html`。
- `src/maildrop/static/home.css` 主页样式和动画。
- 可选 `src/maildrop/static/home.js` 用于粒子鼠标视差和自定义光标。
- 测试覆盖根路径返回 200、包含 XOXO 文案、`/admin` 仍要求 Basic Auth。

不引入前端构建工具，不影响现有后台 CSS。

## 验证

实现完成后运行：

- `.venv/bin/python -m pytest tests/maildrop -q`
- `git diff --check`

并用浏览器检查：

- 桌面首屏校名、校徽、粒子和 hover 动效正常。
- 移动端文字不溢出，导航和卡片可读。
- `/admin`、`/xxxmailmanage`、`/api/health` 不受影响。
