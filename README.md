# TripPal · Cross-Border Travel Assistant

[![CI](https://github.com/zhounongshen/trip-pal-agent/actions/workflows/ci.yml/badge.svg)](https://github.com/zhounongshen/trip-pal-agent/actions)
[![Live Demo](https://img.shields.io/badge/Live_Demo-在线演示-38bdf8)](https://zhounongshen.github.io/trip-pal-agent/demo.html)

<p align="center">
  <a href="README.zh-CN.md">🌐 中文</a>
</p>

A LangGraph agent that answers questions about **Hong Kong / Mainland China holidays & travel** in natural language.

Ask it "How many days is the 2026 National Day holiday?" or "When is the next common long break between HK and Mainland?", and it will **decide which tools to call, query step by step, and answer in natural language**.

**Tech Stack**: Python · LangGraph · DeepSeek V4 Flash (via OpenCode Go) · Local JSON data · FastAPI Web UI

> 📐 See design rationale in [DESIGN.md](DESIGN.md)

---

## ✨ Features

| Capability | Description | Example |
|---|---|---|
| 🇭🇰 HK Public Holidays | Official GovHK data (2025–2027) | "When is the 2027 HK Lunar New Year?" |
| 🇨🇳 CN Holidays | State Council schedule incl. makeup days | "How many days off for the 2026 National Day?" |
| 🤝 Common Breaks | Find overlapping holiday windows between HK & CN | "When is the next common long break?" |
| 📅 Date Calc | Days until a given date | "How many days until the next National Day?" |
| ✂️ Leave Stacking | CN + HK stacking plans (auto-skips makeup days, leverages weekends) | "How to stack leave for the 2026 National Day?" / "HK Christmas leave stacking?" |
| 🧠 Multi-turn Memory | Session history persisted to disk, survives refresh/restart | Follow-up "What about HK?" is understood in context |
| 🌐 Web UI | Chat UI with tool-call trace & quick-ask buttons | — |
| 💬 Interactive CLI | Terminal multi-turn chat | — |

---

## 🎬 Demo

A 85-second walkthrough of the Web UI — holiday lookup, HK/CN common-break matching, and leave-stacking plans:

<p align="center">
  <video src="https://github.com/user-attachments/assets/d3ca2f7f-dd3b-424d-b21c-71a4ad1e7935" controls preload="metadata" width="100%" style="max-width:720px"></video>
</p>

- 🎥 **Video**: `demo_video/trippal_demo_final.mp4` (84s, with English narration & burned-in subtitles)
- 📝 **Subtitles**: [trippal_demo_subtitles.srt](demo_video/trippal_demo_subtitles.srt) (standalone copy)

---

## 🚀 Quick Start

### Requirements

- Python 3.10+ (recommended with [uv](https://docs.astral.sh/uv/))
- An OpenAI-compatible model endpoint (defaults to **OpenCode Go** subscription)

### 1. Clone & Install

```bash
git clone https://github.com/zhounongshen/trip-pal-agent.git
cd trip-pal-agent

# create venv & install deps with uv
uv venv --python 3.12 .venv
uv pip install -r requirements.txt
```

### 2. Prepare Data

```bash
# Option A: use bundled data (already generated)
# Option B: re-fetch from official sources (needs network)
.venv/bin/python scripts/fetch_data.py
```

### 3. Configure Model

**Option A: OpenCode Go subscription (default)**

This project calls DeepSeek V4 Flash via the OpenCode Go subscription by default. If you've logged into opencode on this machine, the program auto-reads the auth key — **no extra config needed**.

**Option B: Other OpenAI-compatible endpoint**

Create `.env` (see `.env.example`):

```bash
OPENAI_API_KEY=sk-your-key
OPENAI_BASE_URL=https://api.deepseek.com/v1
OPENAI_MODEL=deepseek-chat
```

### 4. Run

**Web UI (recommended)**

```bash
PYTHONPATH=src .venv/bin/uvicorn web.app:app --reload --port 8000
```

Open in browser: <http://127.0.0.1:8000>

**Interactive CLI**

```bash
PYTHONPATH=src .venv/bin/python -m trip_pal.cli
```

**One-shot Question**

```bash
PYTHONPATH=src .venv/bin/python -m trip_pal.cli "2026年国庆内地放几天假？"
```

---

## 🧠 How It Works (30s)

```
Your question → LLM plans "what data?"
        → call tools (CN / HK / common breaks)
        → tools return real data
        → LLM synthesizes → final answer
```

- **Model**: DeepSeek V4 Flash (reasoning & language)
- **Tools**: 5 structured tools (CN/HK holidays, common breaks, date calc, leave stacking)
- **Orchestration**: LangGraph `create_react_agent` (reason-act loop)
- **Data**: fetched once into local JSON, no runtime network

See [DESIGN.md](DESIGN.md) §2, §4.

---

## 📂 Project Structure

```
trip-pal-agent/
├── DESIGN.md                # design rationale
├── README.md
├── requirements.txt
├── .env.example             # model config template
├── data/                    # holiday JSON (generated)
│   ├── holidays_hk_2025.json / 2026 / 2027
│   └── holidays_cn_2025.json / 2026
├── scripts/
│   └── fetch_data.py        # fetch official data → JSON
├── src/trip_pal/
│   ├── config.py            # config (model endpoint, key resolution)
│   ├── data_loader.py       # data access layer
│   ├── tools.py             # 5 tools (the "hands")
│   ├── graph.py             # LangGraph orchestration (the "brain")
│   └── cli.py               # CLI entry
└── web/
    ├── app.py               # FastAPI backend
    └── static/index.html    # frontend page
```

---

## 📊 Data Sources (Official)

| Region | Source | Years |
|---|---|---|
| 🇭🇰 HK | [GovHK Public Holidays](https://www.gov.hk/tc/about/abouthk/holiday/2027.htm) | 2025 / 2026 / 2027 |
| 🇨🇳 CN | [State Council Notice](https://www.gov.cn/zhengce/content/202511/content_7047090.htm) | 2025 / 2026 (2027 pending) |

> Data is fetched once into local JSON; no runtime requests to official sites. To refresh: `python scripts/fetch_data.py`.

---

## 🗺️ Roadmap

- [x] Data fetching & JSON modeling
- [x] 5 tools (CN / HK / common breaks / date calc / leave stacking)
- [x] Leave stacking for CN + HK (traditional/simplified & alias matching)
- [x] LangGraph agent loop (multi-step tool calls)
- [x] Multi-turn memory (disk-persisted, survives refresh/restart)
- [x] Web UI with tool-call trace & quick-ask buttons
- [x] Interactive CLI
- [ ] 2027 CN data (once officially released)
- [x] Unit tests (14 pytest) + GitHub Actions CI
- [x] Live demo on GitHub Pages
- [ ] Enhanced HK-CN holiday comparison

---

## 📝 Disclaimer

- Personal learning project; data copyright belongs to respective official agencies.
- Holiday schedules are subject to official final announcements.
- Model answers may err; please verify important decisions manually.

---

*TripPal v0.2 · 2026-08*
