"""TripPal Web 后端（FastAPI）。

作用：接收前端（浏览器页面）发来的问题，调用 agent，返回回答 + 工具轨迹。

多轮记忆：前端每次请求带一个 session_id（存 localStorage），
后端用 SESSIONS 字典保存每个会话的对话历史，实现跨轮记忆。

启动方式：
    cd trip-pal
    PYTHONPATH=src .venv/bin/uvicorn web.app:app --reload --port 8000

然后浏览器打开 http://127.0.0.1:8000
"""
from __future__ import annotations

import sys
import uuid
from pathlib import Path

# 让 Python 能找到 src 下的 trip_pal 包
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from trip_pal.graph import chat

app = FastAPI(title="TripPal", description="两地行程与节假日助手")

# 会话历史存储：{session_id: [历史消息列表]}
# 简单实现（进程内字典）。生产环境应换 Redis/数据库，学习项目够用。
SESSIONS: dict[str, list] = {}


# ---- 请求/响应模型（pydantic 自动校验）----
class AskRequest(BaseModel):
    """前端发来的请求体：{session_id: "...", question: "..."}"""

    session_id: str = ""  # 空则后端自动生成
    question: str


class AskResponse(BaseModel):
    """返回给前端的响应体"""

    session_id: str
    answer: str
    trace: list[dict]


# ---- 核心路由：处理用户问题 ----
@app.post("/ask", response_model=AskResponse)
def handle_ask(req: AskRequest) -> AskResponse:
    """接收问题 → 调 agent → 返回回答和工具轨迹（含多轮记忆）。"""
    # 会话管理：有 session_id 用它的历史，没有则新建
    sid = req.session_id or uuid.uuid4().hex
    history = SESSIONS.setdefault(sid, [])

    # 带历史调用 agent，拿回更新后的历史
    answer, trace, history = chat(history, req.question)
    SESSIONS[sid] = history  # 存回会话存储

    return AskResponse(session_id=sid, answer=answer, trace=trace)


# ---- 静态页面：让浏览器直接访问 index.html ----
# 把 web/static 目录挂载到根路径，访问 / 就是 index.html
app.mount("/", StaticFiles(directory=Path(__file__).resolve().parent / "static", html=True), name="static")
