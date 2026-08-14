"""TripPal Web 后端（FastAPI）。

作用：接收前端（浏览器页面）发来的问题，调用 agent，返回回答 + 工具轨迹。

启动方式：
    cd trip-pal
    PYTHONPATH=src .venv/bin/uvicorn web.app:app --reload --port 8000

然后浏览器打开 http://127.0.0.1:8000
"""
from __future__ import annotations

import sys
from pathlib import Path

# 让 Python 能找到 src 下的 trip_pal 包
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from trip_pal.graph import ask_with_trace

app = FastAPI(title="TripPal", description="两地行程与节假日助手")


# ---- 请求/响应模型（pydantic 自动校验）----
class AskRequest(BaseModel):
    """前端发来的请求体：{question: "..."}"""

    question: str


class AskResponse(BaseModel):
    """返回给前端的响应体"""

    answer: str
    trace: list[dict]


# ---- 核心路由：处理用户问题 ----
@app.post("/ask", response_model=AskResponse)
def handle_ask(req: AskRequest) -> AskResponse:
    """接收问题 → 调 agent → 返回回答和工具轨迹。"""
    answer, trace = ask_with_trace(req.question)
    return AskResponse(answer=answer, trace=trace)


# ---- 静态页面：让浏览器直接访问 index.html ----
# 把 web/static 目录挂载到根路径，访问 / 就是 index.html
app.mount("/", StaticFiles(directory=Path(__file__).resolve().parent / "static", html=True), name="static")
