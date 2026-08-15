# TripPal · 两地行程助手 / Cross-Border Travel Assistant

[![CI](https://github.com/zhounongshen/trip-pal-agent/actions/workflows/ci.yml/badge.svg)](https://github.com/zhounongshen/trip-pal-agent/actions)

> 🎬 **在线演示 / Live Demo**：<https://zhounongshen.github.io/trip-pal-agent/demo.html>
> （纯前端演示，预录回答 + 工具调用轨迹展示，不消耗 API）

> 🌐 **中文 | English** — 一个用自然语言查询 **香港 / 内地节假日与行程** 的 LangGraph Agent
> A LangGraph agent that answers questions about **Hong Kong / Mainland China holidays & travel** in natural language.

问它「2026 年国庆放几天？」「内地和香港下个共同长假期什么时候？」，它会**自己决定调用哪些工具、分步查询、综合两地数据**，最后用自然语言回答你。

Ask it "How many days is the 2026 National Day holiday?" or "When is the next common long break between HK and Mainland?", and it will **decide which tools to call, query step by step, and answer in natural language**.

**技术栈 / Tech Stack**：Python · LangGraph · DeepSeek V4 Flash（via OpenCode Go）· 本地 JSON 数据 · FastAPI Web UI

> 📐 设计意图与架构分析见 / See design rationale in [DESIGN.md](DESIGN.md)

---

## ✨ 功能 / Features

| 能力 / Capability | 说明 / Description | 示例问题 / Example |
|---|---|---|
| 🇭🇰 香港公众假期 / HK Public Holidays | 官方 GovHK 数据（2025–2027）/ Official GovHK data | 「香港 2027 年春节是哪几天？」 |
| 🇨🇳 内地节假日 / CN Holidays | 国务院办公厅安排，含调休 / State Council schedule incl. makeup days | 「2026 年国庆放几天假？」 |
| 🤝 共同假期窗口 / Common Breaks | 自动求两地假期重叠区间 / Find overlapping holiday windows | 「内地和香港下个共同长假期是？」 |
| 📅 日期计算 / Date Calc | 距离某日还有几天 / Days until a date | 「距离下个国庆还有几天？」 |
| ✂️ 拼假建议 / Leave Stacking | 内地 + 香港拼假方案（自动跳过调休补班、利用周末）/ CN + HK stacking plans | 「2026 国庆怎么拼假最划算？」「香港圣诞节如何拼假？」 |
| 🧠 多轮记忆 / Multi-turn Memory | 对话历史持久化到磁盘，刷新/重启不丢 / Session memory persisted to disk | 连续追问「香港呢？」也能理解上文 |
| 🌐 Web UI | 浏览器对话，展示 Agent 工具调用过程 + 快捷提问按钮 / Chat UI with tool-call trace & quick-ask buttons | — |
| 💬 交互式 CLI / Interactive CLI | 终端多轮对话 / Terminal multi-turn chat | — |

---

## 🚀 快速开始 / Quick Start

### 环境要求 / Requirements

- Python 3.10+（推荐用 [uv](https://docs.astral.sh/uv/) 管理 / recommended with [uv](https://docs.astral.sh/uv/)）
- 一个可用的 OpenAI 兼容模型端点 / An OpenAI-compatible model endpoint（默认走 **OpenCode Go 订阅** / defaults to **OpenCode Go**）

### 1. 克隆与安装 / Clone & Install

```bash
git clone https://github.com/zhounongshen/trip-pal-agent.git
cd trip-pal-agent

# 用 uv 创建虚拟环境并安装依赖 / create venv & install deps with uv
uv venv --python 3.12 .venv
uv pip install -r requirements.txt
```

### 2. 准备数据 / Prepare Data

```bash
# 方式 A：直接使用仓库自带的 data/*.json（已生成）/ Option A: use bundled data (already generated)
# 方式 B：重新抓取官方数据（需要网络）/ Option B: re-fetch from official sources (needs network)
.venv/bin/python scripts/fetch_data.py
```

### 3. 配置模型 / Configure Model

**方式 A：使用 OpenCode Go 订阅（默认）/ Option A: OpenCode Go subscription (default)**

本项目默认通过 OpenCode Go 订阅调用 DeepSeek V4 Flash。若你已在本机登录过 opencode，程序会自动读取其认证 key，**无需额外配置**。

This project calls DeepSeek V4 Flash via the OpenCode Go subscription by default. If you've logged into opencode on this machine, the program auto-reads the auth key — **no extra config needed**.

**方式 B：使用其他 OpenAI 兼容端点 / Option B: Other OpenAI-compatible endpoint**

创建 `.env`（参考 / see `.env.example`）：

```bash
OPENAI_API_KEY=sk-你的key / your-key
OPENAI_BASE_URL=https://api.deepseek.com/v1
OPENAI_MODEL=deepseek-chat
```

### 4. 运行 / Run

**Web UI（推荐 / recommended）**

```bash
PYTHONPATH=src .venv/bin/uvicorn web.app:app --reload --port 8000
```

浏览器打开 / Open in browser: <http://127.0.0.1:8000>

**交互式 CLI / Interactive CLI**

```bash
PYTHONPATH=src .venv/bin/python -m trip_pal.cli
```

**单次问答 / One-shot Question**

```bash
PYTHONPATH=src .venv/bin/python -m trip_pal.cli "2026年国庆内地放几天假？"
```

---

## 🧠 它是怎么工作的 / How It Works (30s)

```
你的问题 / Your question → LLM 思考「需要哪些数据？」/ LLM plans "what data?"
        → 调用工具 / call tools (CN / HK / common breaks)
        → 工具返回真实数据 / tools return real data
        → LLM 综合 / LLM synthesizes → 最终回答 / final answer
```

- **模型 / Model**：DeepSeek V4 Flash（判断、规划、组织语言 / reasoning & language）
- **工具 / Tools**：5 个结构化工具 / 5 structured tools（查询内地/香港、共同假期、日期、拼假 / fetch real data & compute plans）
- **编排 / Orchestration**：LangGraph `create_react_agent`（"思考→行动"循环 / reason-act loop）
- **数据 / Data**：一次性从官方抓取为本地 JSON，运行时不依赖网络 / fetched once into local JSON, no runtime network

详见 / See [DESIGN.md](DESIGN.md) §2、§4。

---

## 📂 项目结构 / Project Structure

```
trip-pal-agent/
├── DESIGN.md                # 设计文档 / design rationale
├── README.md
├── requirements.txt
├── .env.example             # 模型配置模板 / model config template
├── data/                    # 节假日 JSON / holiday JSON (generated)
│   ├── holidays_hk_2025.json / 2026 / 2027
│   └── holidays_cn_2025.json / 2026
├── scripts/
│   └── fetch_data.py        # 抓官方数据 → JSON / fetch official data
├── src/trip_pal/
│   ├── config.py            # 配置（模型端点、key 解析）/ config
│   ├── data_loader.py       # 读 JSON → 工具数据 / data access layer
│   ├── tools.py             # 4 个工具（Agent 的「手」）/ tools (the "hands")
│   ├── graph.py             # LangGraph 编排（Agent 的「大脑」）/ graph (the "brain")
│   └── cli.py               # 命令行入口 / CLI entry
└── web/
    ├── app.py               # FastAPI 后端 / backend
    └── static/index.html    # 前端页面 / frontend page
```

---

## 📊 数据来源 / Data Sources（官方权威 / Official）

| 地区 / Region | 来源 / Source | 覆盖年份 / Years |
|---|---|---|
| 🇭🇰 香港 / HK | [GovHK 公众假期 / Public Holidays](https://www.gov.hk/tc/about/abouthk/holiday/2027.htm) | 2025 / 2026 / 2027 |
| 🇨🇳 内地 / CN | [国务院办公厅放假安排 / State Council Notice](https://www.gov.cn/zhengce/content/202511/content_7047090.htm) | 2025 / 2026（2027 待官方发布 / pending） |

> 数据为一次性抓取转存本地 JSON，运行时不请求官方站点。更新数据：`python scripts/fetch_data.py`。
> Data is fetched once into local JSON; no runtime requests to official sites. To refresh: `python scripts/fetch_data.py`.

---

## 🗺️ Roadmap

- [x] 数据抓取与 JSON 建模 / Data fetching & JSON modeling
- [x] 5 个工具 / 5 tools（内地 / HK / 共同假期 / 日期计算 / 拼假）
- [x] 拼假建议支持内地 + 香港（繁简/别名匹配）/ Leave stacking for CN + HK
- [x] LangGraph Agent 循环（多步工具调用 / multi-step tool calls）
- [x] 多轮对话记忆（持久化到磁盘，刷新/重启不丢）/ Multi-turn memory (disk-persisted)
- [x] Web UI（工具轨迹展示 + 快捷提问按钮）/ Web UI with trace & quick-ask
- [x] 交互式 CLI / Interactive CLI
- [ ] 2027 内地数据 / 2027 CN data（官方发布后补 / once released）
- [x] 单元测试（14 个 pytest）+ GitHub Actions CI / Unit tests & CI
- [x] GitHub Pages 在线演示 / Live demo on GitHub Pages
- [ ] 香港共同假期对比增强 / Enhanced HK-CN holiday comparison

---

## 📝 免责声明 / Disclaimer

- 本项目为个人学习项目，数据版权归各官方机构所有 / Personal learning project; data copyright belongs to respective official agencies.
- 节假日安排以官方最终发布为准 / Holiday schedules are subject to official final announcements.
- 模型回答可能出错，重要决策请人工核对 / Model answers may err; please verify important decisions manually.

---

*TripPal v0.1 · 2026-08*
