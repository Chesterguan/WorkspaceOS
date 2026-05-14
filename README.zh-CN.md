# WorkspaceOS

> [English](README.md) · **简体中文**

一个可配置的单界面工作台框架，专为需要长期专注的创作型工作设计。

<p align="center">
  <img src="docs/screenshots/wizard-preview.jpeg" width="700" alt="Onboarding wizard preview pane — Bio Research extension matched, 10 personas + 12 taxonomy nodes generated"/>
  <br/>
  <em>回答 7 个问题 → 匹配扩展 → 实时预览配置 → 一键应用。</em>
</p>

回答 7 个问题。框架根据答案生成专属工作台——顾问团、知识分类、提示词风格、界面布局，之后你可以继续自定义。**领域内容是即插即用的**，通过扩展文件夹实现。框架今天自带两个扩展（AI 研究、生物研究），写一个新的只需要一个 YAML 文件夹。

参考实现 **ProjectScribe** 是维护者用来构建 WorkspaceOS 本身的日常 AI 联合创始人工具。

> Phase 1 = 内容扩展（顾问角色、分类法、提示词）。
> Phase 2 = 能力扩展（Gmail / 日历 / Slack 数据接入）。
> Phase 2 的 schema 已经预留好，所以今天写的清单未来仍然兼容。

---

## 它能做什么

工作台包含六个可选界面，每个都由你的领域配置驱动：

| 字母 | 界面        | 功能 |
|------|-------------|------|
| **A**  | Advisor     | 与联合创始人顾问团对话。每条消息 3–4 位顾问参与点评。 |
| **R**  | Research    | 学术 / 领域评审团的并行评议。5–6 位评审，从不同视角发声。 |
| **D**  | Drafts      | 博客和社交媒体草稿（按项目，分页）。 |
| **P**  | Papers      | 研究论文——单篇 + 作品集。多智能体 v2 流水线。 |
| **K**  | Knowledge   | 跨项目的知识图谱——决策 / 主张 / 假设从对话中自动抽取。 |
| **W**  | Worklog     | 周 / 月 / 季度进度报告。 |

外加 `⌘K` 命令面板、可滑出的项目检查器，以及右侧 TUI 日志，实时显示每一次 AI 调用、同步与抽取。

## 截图

<table>
<tr>
<td width="50%">
  <img src="docs/screenshots/wizard-step1.jpeg" alt="Wizard step 1 — domain question"/>
  <br/><sub><b>引导向导 · 第 1 步。</b>自由文本的领域描述决定扩展匹配。</sub>
</td>
<td width="50%">
  <img src="docs/screenshots/wizard-wait.jpeg" alt="Wait state — 5-chapter SVG tutorial animation"/>
  <br/><sub><b>等待界面。</b>生成期间循环播放 5 章 SVG 教程动画，SSE 字幕实时更新。</sub>
</td>
</tr>
<tr>
<td width="50%">
  <img src="docs/screenshots/wizard-preview.jpeg" alt="Preview pane with Bio Research extension matched"/>
  <br/><sub><b>预览面板。</b>显示匹配的扩展徽章、顾问、分类标签，可展开原始 YAML。</sub>
</td>
<td width="50%">
  <img src="docs/screenshots/bench-research.jpeg" alt="Research surface — bio-research persona panel"/>
  <br/><sub><b>Research 界面。</b>应用 Bio Research 扩展后，Drew Endy / George Church / Jay Keasling / Doudna / Topol / Tim Lu 出现在评审栏。</sub>
</td>
</tr>
</table>

## 快速开始

**前置依赖：** Docker。安装
[Docker Desktop](https://www.docker.com/products/docker-desktop/)（macOS / Windows / Linux）
或 [OrbStack](https://orbstack.dev/)（macOS 上更快）。在继续之前，确认终端中 `docker compose` 可用。

```bash
git clone https://github.com/Chesterguan/WorkspaceOS.git
cd WorkspaceOS

cp .env.example .env
# 编辑 .env —— 最低要求是 GEMINI_API_KEY，其它都有合理默认值

docker compose up --build -d

# 工作台:    http://localhost:4000
# 后端 API:  http://localhost:9000/docs
```

首次打开会跳转到 `/login`。注册账号后，`/onboarding` 会引导你回答 7 个问题并生成工作台。你也可以跳过向导，使用默认配置。

## 扩展是怎么"插"上来的

一个扩展就是 `config/extensions/<id>/` 下的一个文件夹：

```
config/extensions/bio-research/
├── manifest.yaml         # 匹配规则 + 版本 + 路径引用
├── personas/
│   ├── cofounder.yaml    # 3–4 位联合创始人角色
│   └── research.yaml     # 5–6 位研究评审
├── taxonomies/extra.yaml # 在基础 7 类之外新增节点类型
└── prompts/worklog/
    ├── weekly.txt
    ├── monthly.txt
    └── quarterly.txt
```

`manifest.yaml` 就是普通 YAML——无需 Python、无需 JS、无需构建步骤：

```yaml
id: bio-research
name: Bio Research
description: 用于湿实验室生物学和生物代工厂的顾问团 + 分类法。
version: 0.1.0
author: workspaceos
matches:
  domain_keywords: [bio, biotech, biofoundry, synthetic biology, strain, crispr]
  audience_any: [peer_researchers]
  outputs_any: [papers]
personas:
  cofounder: ./personas/cofounder.yaml
  research:  ./personas/research.yaml
taxonomy_extra: ./taxonomies/extra.yaml
worklog_templates:
  weekly:    ./prompts/worklog/weekly.txt
  monthly:   ./prompts/worklog/monthly.txt
  quarterly: ./prompts/worklog/quarterly.txt
```

**新增一个扩展**就是放一个文件夹：

1. `cp -r config/extensions/bio-research config/extensions/your-domain`
2. 编辑 `manifest.yaml`——改 `id`、`name`、`matches.domain_keywords`
3. 按你的领域改写角色 / 分类 / 提示词文件
4. 重启后端（`docker compose restart backend`）

向导的匹配器会拿用户的回答给每个扩展打分：
- `domain_keywords` 子串命中 = 每次 +2
- `audience_any` 重叠 = 每次 +1
- `outputs_any` 重叠 = 每次 +1

阈值是 2。分数最高且超过阈值的扩展胜出。没有匹配 → Gemini 合成 → 确定性的桶兜底。

完整的扩展编写指南见 [CONTRIBUTING.md](CONTRIBUTING.md)。

## 能力扩展（v0.2.1）

除了"内容"（角色、分类、提示词），扩展还能声明**能力**——运行时挂钩，用来拉取数据、添加面板入口、给条目加上下文按钮。能力代码住在框架内（`backend/app/capabilities/`），按名字注册，清单引用名字。

目前可用的三种能力类型：

- **`ingest_source`** —— 按计划轮询的异步运行器。向 TUI 日志发送事件、向知识图谱插入节点。示例：`local-files-watcher` 每 30 秒扫一遍目录，每个新文件生成一个 `file_ingested` 节点。
- **`slash_command`** —— `⌘K` 命令面板入口。两种处理方式：`api_call` 调用注册的后端 runner；`navigate` 路由跳转。示例：「立即扫描本地文件」（api_call）、「打开知识图谱」（navigate）。
- **`action_button`** —— 渲染在某个目标条目（当前是 `knowledge_node`）上的上下文按钮。用 `visible_when` 按字段过滤。示例：「标记为决策」只在 claim / hypothesis / insight / question 节点上显示。

自带扩展：

- **`local-files-watcher`** —— `ingest_source: local_files`。监视 `WORKSPACE_HOST_PATH` 下的目录，按 mtime+大小去重，每次最多 100 个文件，跳过 dot 目录 / `node_modules` / `.git`。
- **`macos-mail`** —— `ingest_source: macos_mail`。已声明；通过宿主机的 AppleScript bridge（`scripts/outlook_bridge/install.sh`）运行，读取 Apple Mail + Outlook for Mac，POST 到 `/skills/local-ingest/items`。容器内没有代码——因为 Mail.app 在 Docker 里访问不到。
- **`bench-extras`** —— 工具包：2 个 slash command + 2 个 action button。可作为编写自己扩展时的模板。

### 用户在哪里发现能力

| 位置 | 显示内容 |
|---|---|
| **设置 → Capabilities 标签页** | 所有已声明能力的只读列表，按类型分组，带 `runtime ready` / `declared` 徽章和来源扩展。「已安装"的视图。 |
| **⌘K 命令面板** | Slash command 与内置入口混排，可输入过滤、点击触发。 |
| **就近** | Action button 直接渲染在目标条目上——比如知识节点详情面板里的「Extension actions」一行。`visible_when` 让菜单不至于乱。 |

### 编写能力

完整作者指南见 [CONTRIBUTING.md](CONTRIBUTING.md)。每种类型的快速结构：

```yaml
# config/extensions/your-id/manifest.yaml
capabilities:
  # 1. 按计划把外部数据拉进工作台
  - kind: ingest_source
    name: my_runner                   # ← backend/app/capabilities/registry.py 里的键
    config:
      poll_interval_seconds: 60
      # 你的 runner 的配置字段

  # 2. 面板入口 (⌘K)
  - kind: slash_command
    name: do_thing
    config:
      label: "Do the thing"
      keywords: [thing, do]
      icon: zap
      # handler_kind: api_call    → POST 到 handler_target
      # handler_kind: navigate    → router.push(handler_target)
      handler_kind: api_call
      handler_target: /capabilities/runners/do_thing/trigger

  # 3. 某个条目类型上的按钮
  - kind: action_button
    name: tag_with_x
    config:
      label: "Tag with X"
      target: knowledge_node          # 这个按钮挂到哪种条目渲染器
      handler_kind: api_call
      visible_when:                   # AND-of-OR 过滤
        node_type: [claim, hypothesis]
```

然后在 `backend/app/capabilities/registry.py`（或 `slash.py` / `actions.py`）注册 Python runner / handler，提 PR。信任模型是"注册表 = 审计面"：能力代码与框架同源、清单按名字引用 runner。不允许任意文件投放、不允许 `eval`、不允许扩展注入 JSX。

## 向导是怎么工作的

1. **用户在 `/onboarding` 回答 7 个问题**：领域（自由文本）、主要产出、受众、理想顾问团、要追踪的东西、节奏、阶段。

2. **后端匹配扩展**：用每个已加载扩展的 `matches` 规则给答案打分。

3. **生成器构造配置**：
   - 命中扩展 → 把其 bundled 文件原样拼入；发出 "Matched extension: X (score N)" 事件。
   - 否则若设置了 `GEMINI_API_KEY` → 一次 LLM 调用返回角色 + 分类增量 + 标语。
   - 否则 → 确定性的桶 stub（CS / 生物 / 经济学）。

4. **SSE 流**把进度字幕推给向导的等待动画（5 章 SVG 教程独立循环）。同样的事件也流向工作台右侧的 TUI 日志，所以用户回到工作台后能看到刚才发生了什么。

5. **预览面板**显示生成的角色、分类标签、worklog 模板样例、原始 YAML 展开。**Apply** 写入 `config/`，触发实时重载，并把用户标记为已上手。**Regenerate** 重新生成。

总耗时：扩展命中约 15 秒，Gemini 约 10 秒，桶兜底瞬时。

## 架构

- **前端** —— Next.js 16（App Router、Suspense、`proxy.ts` 中间件）、Tailwind v4、shadcn/ui、motion（Framer）、React Flow + dagre 渲染知识图谱。端口 **4000**。
- **后端** —— FastAPI（异步）、PostgreSQL 15 + pgvector（768 维 IVFFlat）、Server-Sent Events 驱动工作台日志和向导生成过程。端口 **9000**。
- **AI** —— 混合。本地 Ollama（`nomic-embed-text`）做嵌入；Gemini 做生成和向导兜底；OpenAI 给论文圆桌评审（可选）。
- **部署** —— Docker Compose，三个服务（`db`、`backend`、`frontend`）在 `workspaceos` 网络里。鉴权：用户走 JWT，脚本和 SSE 查询参数走 `X-API-Key`。

## 需要的 vs 可选的配置

| 必需 | 可选 |
|---|---|
| **Gemini API key** —— 聊天 / 草稿 / 论文 / 抽取 / 嵌入兜底。免费 tier 够用。 | **OpenAI key** —— 只给论文圆桌评审使用。没有它论文仍可生成。 |
| | **Ollama** 本地运行 —— 免费本地嵌入，没装时回落到 Gemini。 |
| | **GitHub token** —— 仓库同步、深度上下文、发布。 |
| | **LinkedIn / Dev.to / Hashnode keys** —— 多平台发布。 |

所有 API key 都可以在 Settings 页面里运行时配置（Fernet 加密存数据库），不一定要写 `.env`。

## 路线图

- **v0.2.2 —— 更多能力运行器。** Gmail（OAuth）、Calendar（CalDAV / Google）、Slack、Notion。欢迎贡献。
- **v0.2.2 —— 更多能力类型。** `slash_command` / `action_button` 已经活跃；`surface_widget`（嵌入现有界面的子组件）即将就位。
- **v0.3 —— 能力 runner 作为 Python 包发布。** 不再需要 PR 进核心仓——`pip install workspaceos-gmail-ingest`，runner 自动注册。架构今天已经为此预留了 `discover_entry_points()` 钩子。
- **v0.4 —— 界面类型作为注册表。** 扩展自带 React 组件 + 清单声明，运行时注册。架构今天已经表驱动了；v0.4 是激活而非重写。
- **更多内容扩展** —— `indie-founder`、`phd-student`、`engineering-manager`。
- **Settings → "Personalize"** —— 用上次的答案重新跑一遍向导。

## 现状

OSS 项目，MIT 许可（见 [LICENSE](LICENSE)）。工作台、六个界面、扩展框架、引导向导、知识图谱、worklog 生成器、论文 v2 流水线今天都能用。多租户部署尚未加固——见 [CONTRIBUTING.md](CONTRIBUTING.md) 里的安全说明。

## 技术说明

- **Next.js 16 兼容** —— 使用 `proxy.ts`（而非废弃的 `middleware.ts`），`useSearchParams` 包在 `<Suspense>` 里，动态参数用 `use()`。
- **知识图谱去重** —— 单用户的 `asyncio.Lock` 串行化并发顾问抽取，让同一轮对话的余弦近邻节点合并而不重复。
- **事件 SSE 鉴权** —— 回退到 `?api_key=` 查询参数，因为 `EventSource` 不能设置自定义 header。单用户演示场景没问题，多租户部署需要短期 SSE token 交换机制。
- **遵循 reduced motion** —— 全局尊重 WCAG 2.3.3。

## 贡献

欢迎 PR——尤其是**新的内容扩展**。完整作者指南见 [CONTRIBUTING.md](CONTRIBUTING.md)。

## 许可

MIT。见 [LICENSE](LICENSE)。
