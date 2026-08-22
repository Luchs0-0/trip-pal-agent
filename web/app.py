"""TripPal Web 后端（FastAPI）。

作用：接收前端（浏览器页面）发来的问题，调用 agent，返回回答 + 工具轨迹。

多轮记忆：
  - 前端每次请求带 session_id（存 localStorage）
  - 后端按 session_id 保存对话历史，实现跨轮记忆
  - 历史持久化到磁盘（web/sessions/*.json），重启服务不丢

启动方式：
    cd trip-pal
    PYTHONPATH=src .venv/bin/uvicorn web.app:app --reload --port 8000

然后浏览器打开 http://127.0.0.1:8000
"""

from __future__ import annotations

import json
import sys
import uuid
from pathlib import Path

# 让 Python 能找到 src 下的 trip_pal 包
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from trip_pal.graph import stream_chat

app = FastAPI(title="TripPal", description="两地行程与节假日助手")

# ---------------------------------------------------------------------------
# 会话存储：按 session_id 保存对话历史，持久化到磁盘
# ---------------------------------------------------------------------------
SESSIONS_DIR = Path(__file__).resolve().parent / "sessions"
SESSIONS_DIR.mkdir(exist_ok=True)


def _session_path(sid: str) -> Path:
    """每个会话一个 JSON 文件：web/sessions/{sid}.json"""
    return SESSIONS_DIR / f"{sid}.json"


def load_history(sid: str) -> list:
    """从磁盘加载某会话的历史（统一格式 dict 列表，无则空列表）。"""
    path = _session_path(sid)
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data.get("messages", [])
    except (OSError, ValueError):
        return []


def save_history(sid: str, messages: list) -> None:
    """把某会话的历史写入磁盘（消息已是可 JSON 化的 dict 列表）。"""
    path = _session_path(sid)
    path.write_text(
        json.dumps({"messages": messages}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def delete_history(sid: str) -> None:
    """删除某会话的历史文件（配合前端「清空」按钮）。"""
    path = _session_path(sid)
    if path.exists():
        path.unlink()


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


class HistoryResponse(BaseModel):
    """返回某会话的对话历史（供前端刷新后恢复界面）"""

    messages: list[dict]  # [{"role": "user"/"assistant", "content": "..."}, ...]


class ClearResponse(BaseModel):
    """清空会话的响应体"""

    session_id: str
    cleared: bool


# ---- 核心路由：处理用户问题（SSE 流式）----
@app.post("/ask")
async def handle_ask(req: AskRequest):
    """接收问题 → 流式调 agent → 以 SSE 逐步推送事件。

    事件流（每行 data: <json>，空行分隔）：
      {"type":"tool_start","tool":...,"args":...}
      {"type":"tool_result","tool":...,"result":...}
      {"type":"token","text":...}
      {"type":"done","answer":...,"trace":[...]}
    前端用 fetch + ReadableStream 逐块读取，实时渲染。
    """
    sid = req.session_id or uuid.uuid4().hex
    history = load_history(sid)

    async def event_gen_with_save():
        nonlocal history
        yield f"data: {json.dumps({'type': 'session', 'session_id': sid})}\n\n"
        final_answer = ""
        final_trace: list[dict] = []
        async for event in stream_chat(history, req.question):
            if event.get("type") == "done":
                final_answer = event.get("answer", "")
                final_trace = event.get("trace", [])
            yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
        # 持久化：旧历史 + 本轮（user 问题 + assistant 完整回答，带 trace）
        history = history + [
            {"role": "user", "content": req.question, "trace": []},
            {"role": "assistant", "content": final_answer, "trace": final_trace},
        ]
        save_history(sid, history)

    return StreamingResponse(
        event_gen_with_save(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ---- 历史查询：前端刷新后向后端要回对话记录 ----
@app.get("/history", response_model=HistoryResponse)
def get_history(session_id: str) -> HistoryResponse:
    """根据 session_id 返回该会话的对话历史（含工具轨迹，供界面恢复）。"""
    history = load_history(session_id)
    # 统一格式下，每条消息已是 {role, content, trace}，直接给前端
    msgs = [
        {
            "role": m.get("role", ""),
            "content": m.get("content", ""),
            "trace": m.get("trace", []),
        }
        for m in history
    ]
    return HistoryResponse(messages=msgs)


# ---- 清空会话：配合前端「清空」按钮 ----
@app.post("/clear", response_model=ClearResponse)
def clear_session(session_id: str) -> ClearResponse:
    """删除某会话的历史，让「清空」按钮真正清掉后端记忆。"""
    delete_history(session_id)
    return ClearResponse(session_id=session_id, cleared=True)


# ---- 静态页面：让浏览器直接访问 index.html ----
# 把 web/static 目录挂载到根路径，访问 / 就是 index.html
app.mount(
    "/",
    StaticFiles(directory=Path(__file__).resolve().parent / "static", html=True),
    name="static",
)
