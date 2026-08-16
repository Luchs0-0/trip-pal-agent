# TripPal · 两地行程助手

[![CI](https://github.com/zhounongshen/trip-pal-agent/actions/workflows/ci.yml/badge.svg)](https://github.com/zhounongshen/trip-pal-agent/actions)
[![Live Demo](https://img.shields.io/badge/Live_Demo-在线演示-38bdf8)](https://zhounongshen.github.io/trip-pal-agent/demo.html)

<p align="center">
  <a href="README.md">🌐 English</a>
</p>

一个用自然语言查询 **香港 / 内地节假日与行程** 的 LangGraph Agent。

问它「2026 年国庆放几天？」「内地和香港下个共同长假期什么时候？」，它会**自己决定调用哪些工具、分步查询、综合两地数据**，最后用自然语言回答你。

**技术栈**：Python · LangGraph · DeepSeek V4 Flash（经 OpenCode Go）· 本地 JSON 数据 · FastAPI Web UI

> 📐 设计意图与架构分析见 [DESIGN.md](DESIGN.md)

---

## ✨ 功能

| 能力 | 说明 | 示例问题 |
|---|---|---|
| 🇭🇰 香港公众假期 | 官方 GovHK 数据（2025–2027）| 「香港 2027 年春节是哪几天？」 |
| 🇨🇳 内地节假日 | 国务院办公厅安排，含调休 | 「2026 年国庆放几天假？」 |
| 🤝 共同假期窗口 | 自动求两地假期重叠区间 | 「内地和香港下个共同长假期是？」 |
| 📅 日期计算 | 距离某日还有几天 | 「距离下个国庆还有几天？」 |
| ✂️ 拼假建议 | 内地 + 香港拼假方案（自动跳过调休补班、利用周末）| 「2026 国庆怎么拼假最划算？」「香港圣诞节如何拼假？」 |
| 🧠 多轮记忆 | 对话历史持久化到磁盘，刷新/重启不丢 | 连续追问「香港呢？」也能理解上文 |
| 🌐 Web UI | 浏览器对话，**实时流式展示工具调用过程**（SSE）+ 快捷提问按钮 | — |
| 💬 交互式 CLI | 终端多轮对话 | — |

---

## 🎬 演示视频

85 秒 Web UI 完整演示——节假日查询、两地共同假期匹配、拼假方案生成：

<p align="center">
  <video src="https://github.com/user-attachments/assets/d3ca2f7f-dd3b-424d-b21c-71a4ad1e7935" controls preload="metadata" width="100%" style="max-width:720px"></video>
</p>

- 🎥 **视频**：`demo_video/trippal_demo_final.mp4`（84 秒，英文旁白 + 内嵌英文字幕）
- 📝 **字幕文件**：[trippal_demo_subtitles.srt](demo_video/trippal_demo_subtitles.srt)

---

## 🚀 快速开始

### 环境要求

- Python 3.10+（推荐用 [uv](https://docs.astral.sh/uv/) 管理）
- 一个可用的 OpenAI 兼容模型端点（默认走 **OpenCode Go 订阅**）

### 1. 克隆与安装

```bash
git clone https://github.com/zhounongshen/trip-pal-agent.git
cd trip-pal-agent

# 用 uv 创建虚拟环境并安装依赖
uv venv --python 3.12 .venv
uv pip install -r requirements.txt
```

### 2. 准备数据

```bash
# 方式 A：直接使用仓库自带的 data/*.json（已生成）
# 方式 B：重新抓取官方数据（需要网络）
.venv/bin/python scripts/fetch_data.py
```

### 3. 配置模型

**方式 A：使用 OpenCode Go 订阅（默认）**

本项目默认通过 OpenCode Go 订阅调用 DeepSeek V4 Flash。若你已在本机登录过 opencode，程序会自动读取其认证 key，**无需额外配置**。

**方式 B：使用其他 OpenAI 兼容端点**

创建 `.env`（参考 `.env.example`）：

```bash
OPENAI_API_KEY=sk-你的key
OPENAI_BASE_URL=https://api.deepseek.com/v1
OPENAI_MODEL=deepseek-chat
```

### 4. 运行

**Web UI（推荐）**

```bash
PYTHONPATH=src .venv/bin/uvicorn web.app:app --reload --port 8000
```

浏览器打开 <http://127.0.0.1:8000>

**交互式 CLI**

```bash
PYTHONPATH=src .venv/bin/python -m trip_pal.cli
```

**单次问答**

```bash
PYTHONPATH=src .venv/bin/python -m trip_pal.cli "2026年国庆内地放几天假？"
```

---

## 🧠 它是怎么工作的（30 秒版）

```
你的问题 → LLM 思考「需要哪些数据？」
        → 调用工具（查内地/香港/共同假期）
        → 工具返回真实数据
        → LLM 综合 → 最终回答
```

- **模型**：DeepSeek V4 Flash（判断、规划、组织语言）
- **工具**：5 个结构化工具（查内地/香港、共同假期、日期、拼假）
- **编排**：LangGraph `create_react_agent`（"思考→行动"循环）
- **数据**：一次性从官方抓取为本地 JSON，运行时不依赖网络

详见 [DESIGN.md](DESIGN.md) §2、§4。

---

## 📂 项目结构

```
trip-pal-agent/
├── DESIGN.md                # 设计文档
├── README.md
├── requirements.txt
├── .env.example             # 模型配置模板
├── data/                    # 节假日 JSON（抓取后生成）
│   ├── holidays_hk_2025.json / 2026 / 2027
│   └── holidays_cn_2025.json / 2026
├── scripts/
│   └── fetch_data.py        # 抓官方数据 → JSON
├── src/trip_pal/
│   ├── config.py            # 配置（模型端点、key 解析）
│   ├── data_loader.py       # 读 JSON → 工具数据
│   ├── tools.py             # 5 个工具（Agent 的「手」）
│   ├── graph.py             # LangGraph 编排（Agent 的「大脑」）
│   └── cli.py               # 命令行入口
└── web/
    ├── app.py               # FastAPI 后端
    └── static/index.html    # 前端页面
```

---

## 📊 数据来源（官方权威）

| 地区 | 来源 | 覆盖年份 |
|---|---|---|
| 🇭🇰 香港 | [GovHK 公众假期](https://www.gov.hk/tc/about/abouthk/holiday/2027.htm) | 2025 / 2026 / 2027 |
| 🇨🇳 内地 | [国务院办公厅放假安排](https://www.gov.cn/zhengce/content/202511/content_7047090.htm) | 2025 / 2026（2027 待官方发布）|

> 数据为一次性抓取转存本地 JSON，运行时不请求官方站点。更新数据：`python scripts/fetch_data.py`。

---

## 🗺️ Roadmap

- [x] 数据抓取与 JSON 建模
- [x] 5 个工具（内地 / 香港 / 共同假期 / 日期计算 / 拼假）
- [x] 拼假建议支持内地 + 香港（繁简/别名匹配）
- [x] LangGraph Agent 循环（多步工具调用）
- [x] 多轮对话记忆（持久化到磁盘，刷新/重启不丢）
- [x] Web UI（工具轨迹展示 + 快捷提问按钮）
- [x] 交互式 CLI
- [ ] 2027 内地数据（官方发布后补）
- [x] 单元测试（14 个 pytest）+ GitHub Actions CI
- [x] GitHub Pages 在线演示
- [ ] 香港共同假期对比增强

---

## 📝 免责声明

- 本项目为个人学习项目，数据版权归各官方机构所有；
- 节假日安排以官方最终发布为准；
- 模型回答可能出错，重要决策请人工核对。

---

*TripPal v0.2 · 2026-08*
