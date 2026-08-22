"""LangGraph 编排：把模型 + 工具接成 Agent 循环。

这是 Agent 的「大脑与手的连接层」。核心概念：

  - create_react_agent(model, tools, prompt)
    内置完整的「ReAct 循环」：模型思考 → 需要工具？→ 执行工具 → 结果回填
    → 再思考…… 直到模型认为可以回答。

  - 这里的 prompt 是系统提示，告诉模型「你是谁、能用什么、怎么选工具」。

对外提供 build_agent()：返回一个可调用的 agent 对象。
"""

from __future__ import annotations

from langchain_openai import ChatOpenAI
from langgraph.prebuilt import create_react_agent

from .config import settings
from .tools import ALL_TOOLS, TOOL_GUIDE

# 系统提示：agent 的人设 + 工具使用指引
SYSTEM_PROMPT = f"""你是 TripPal，一个香港/内地两地行程与节假日助手。

你的职责：
- 用中文回答用户关于两地节假日、假期安排、行程规划的问题；
- 涉及数据时，必须调用工具获取真实数据，不要凭记忆编造；
- 需要两地数据时，分别调用对应工具，再综合回答。

{TOOL_GUIDE}

[工具选择铁律]
- 涉及「拼假 / 请假连休 / 怎么请最划算」的问题（无论内地还是香港），
  必须调用 suggest_leave_stacking 获取拼假方案，严禁自己推算拼假天数；
  因为它内部处理了「跳过调休补班日、利用周末」等复杂规则，自己推算会出错
  （例如误把补班日当可请假日）。
- 若 suggest_leave_stacking 不支持该地区（如香港），先用对应查询工具
  拿到假期数据，再基于数据说明，并注明「拼假需结合公司年假规则」。

回答要求：
- 简洁、准确、友好；
- 给出日期时注明星期；
- 若数据覆盖不到，如实说明。
"""


def build_agent():
    """构建并返回 TripPal Agent。

    Returns:
        一个可调用对象：agent.invoke({"messages": [{"role": "user", "content": "..."}]})
    """
    llm = ChatOpenAI(
        model=settings.model,
        api_key=settings.resolved_api_key() or None,
        base_url=settings.openai_base_url,
        temperature=settings.temperature,
    )
    agent = create_react_agent(
        model=llm,
        tools=ALL_TOOLS,
        prompt=SYSTEM_PROMPT,
    )
    return agent


def ask(question: str) -> str:
    """最简封装：给一句话，返回回答文本。"""
    agent = build_agent()
    result = agent.invoke({"messages": [{"role": "user", "content": question}]})
    # create_react_agent 的最终结果在 messages 最后一条 AI 消息里
    messages = result.get("messages", [])
    for msg in reversed(messages):
        if getattr(msg, "type", "") == "ai":
            return str(msg.content)
    return "（Agent 没有返回有效回答）"


def chat(history: list, question: str) -> tuple[str, list[dict], list]:
    """多轮对话：接收历史消息 + 新问题，返回（回答, 工具轨迹, 更新后的历史）。

    这是「多轮记忆」的核心函数。

    历史格式（统一，界面与存储共用）：
      [{"role": "user", "content": "...", "trace": []},
       {"role": "assistant", "content": "...", "trace": [{tool, args, result}, ...]},
       ...]
      - role: "user" 或 "assistant"
      - trace: 该条 assistant 回答对应的工具调用轨迹（user 消息为空列表）

    函数内部会把历史转成 LangChain 消息发给 agent（agent 只需要 role+content，
    trace 是给界面展示用的，不影响模型推理）。
    """
    from langchain_core.messages import AIMessage, HumanMessage

    agent = build_agent()

    # 1) 把统一格式历史转成 LangChain 消息（HumanMessage / AIMessage）
    lc_messages = []
    for m in history:
        if m.get("role") == "user":
            lc_messages.append(HumanMessage(content=m.get("content", "")))
        elif m.get("role") == "assistant":
            lc_messages.append(AIMessage(content=m.get("content", "")))
    # 2) 追加本轮新问题
    lc_messages.append(HumanMessage(content=question))

    result = agent.invoke({"messages": lc_messages})
    messages = result.get("messages", [])

    # 3) 提取回答 + 工具轨迹（逻辑与 ask_with_trace 相同）
    trace: list[dict] = []
    answer = "（Agent 没有返回有效回答）"
    for msg in messages:
        mtype = getattr(msg, "type", "")
        if mtype == "ai" and getattr(msg, "tool_calls", None):
            for tc in msg.tool_calls:
                trace.append(
                    {
                        "tool": tc.get("name", ""),
                        "args": tc.get("args", {}),
                        "result": "（等待执行）",
                    }
                )
        elif mtype == "tool":
            for item in reversed(trace):
                if item["tool"] == msg.name and item["result"] == "（等待执行）":
                    item["result"] = str(msg.content)[:500]
                    break
        elif mtype == "ai" and not getattr(msg, "tool_calls", None):
            answer = str(msg.content)

    # 4) 更新后的历史 = 旧历史 + 本轮（user 问题 + assistant 回答，带 trace）
    history_new = list(history) + [
        {"role": "user", "content": question, "trace": []},
        {"role": "assistant", "content": answer, "trace": trace},
    ]
    return answer, trace, history_new


def ask_with_trace(question: str) -> tuple[str, list[dict]]:
    """返回 (回答, 工具调用轨迹)，供 CLI / Web 展示 agent 思考过程。

    轨迹元素形如：
      {"tool": "get_holidays_cn", "args": {"year": 2026, "month": 10},
       "result": "{...}"}   ← result 为工具返回的字符串形式
    """
    agent = build_agent()
    result = agent.invoke({"messages": [{"role": "user", "content": question}]})
    messages = result.get("messages", [])

    trace: list[dict] = []
    answer = "（Agent 没有返回有效回答）"
    for msg in messages:
        mtype = getattr(msg, "type", "")
        if mtype == "ai" and getattr(msg, "tool_calls", None):
            for tc in msg.tool_calls:
                trace.append(
                    {
                        "tool": tc.get("name", ""),
                        "args": tc.get("args", {}),
                        "result": "（等待执行）",
                    }
                )
        elif mtype == "tool":
            for item in reversed(trace):
                if item["tool"] == msg.name and item["result"] == "（等待执行）":
                    item["result"] = str(msg.content)[:500]
                    break
        elif mtype == "ai" and not getattr(msg, "tool_calls", None):
            answer = str(msg.content)
    return answer, trace


async def stream_chat(history: list, question: str):
    """流式多轮对话：逐步产出事件，供 Web 端实时展示。

    与 chat() 不同，这里用 agent.astream() 流式执行，边跑边 yield。

    事件类型：
      {"type": "tool_start", "tool": "...", "args": {...}}
          —— 模型决定调用某工具（前端显示"正在调用…"）
      {"type": "tool_result", "tool": "...", "result": "..."}
          —— 工具执行完成（前端显示结果摘要）
      {"type": "token", "text": "..."}
          —— 回答内容（节点级：一次给全；opencode-go 端点不逐字流）
      {"type": "done", "answer": "...", "trace": [...]}
          —— 全部完成（前端把完整回答 + 轨迹存入历史）

    实测说明：opencode-go 端点支持 SSE streaming，但 deepseek-v4-flash
    是推理模型，「有工具调用」时 LangChain 的 messages 模式不吐 content，
    所以这里用节点级流（astream 默认模式）：工具事件实时 + 回答一次到位。
    这样只调用一次模型，不浪费配额。
    """
    from langchain_core.messages import AIMessage, HumanMessage

    agent = build_agent()

    # 1) 历史转 LangChain 消息（与 chat() 相同：只用 role+content）
    lc_messages = []
    for m in history:
        if m.get("role") == "user":
            lc_messages.append(HumanMessage(content=m.get("content", "")))
        elif m.get("role") == "assistant":
            lc_messages.append(AIMessage(content=m.get("content", "")))
    lc_messages.append(HumanMessage(content=question))

    # 2) 流式执行（节点粒度）：astream() 每跑完一个节点 yield 一次
    #    实测 chunk 结构：
    #      {"agent": {"messages": [AIMessage(tool_calls=...)]}}  ← 要调工具
    #      {"tools": {"messages": [ToolMessage(...)]}}          ← 工具结果
    #      {"agent": {"messages": [AIMessage(最终回答)]}}        ← 完成
    #    注意：带 tool_calls 的 ai 消息可能带 content（"我来查一下"），
    #    那不是最终回答，必须跳过。
    trace: list[dict] = []
    answer_parts: list[str] = []
    async for chunk in agent.astream({"messages": lc_messages}):
        if not isinstance(chunk, dict):
            continue
        # 模型输出节点（agent）
        inner = chunk.get("agent")
        if isinstance(inner, dict):
            for msg in inner.get("messages", []):
                mtype = getattr(msg, "type", "")
                if mtype == "ai" and getattr(msg, "tool_calls", None):
                    for tc in msg.tool_calls:
                        entry = {
                            "tool": tc.get("name", ""),
                            "args": tc.get("args", {}),
                            "result": "（等待执行）",
                        }
                        trace.append(entry)
                        yield {
                            "type": "tool_start",
                            "tool": entry["tool"],
                            "args": entry["args"],
                        }
                elif mtype == "ai" and not getattr(msg, "tool_calls", None):
                    if msg.content:
                        answer_parts.append(str(msg.content))
                        yield {"type": "token", "text": str(msg.content)}
        # 工具执行节点（tools）
        tools_inner = chunk.get("tools")
        if isinstance(tools_inner, dict):
            for msg in tools_inner.get("messages", []):
                if getattr(msg, "type", "") == "tool":
                    for entry in reversed(trace):
                        if (
                            entry["tool"] == msg.name
                            and entry["result"] == "（等待执行）"
                        ):
                            entry["result"] = str(msg.content)[:500]
                            yield {
                                "type": "tool_result",
                                "tool": msg.name,
                                "result": entry["result"],
                            }
                            break

    # 3) 全部完成：拼出完整回答，带 trace 一起收尾
    answer = "".join(answer_parts) or "（Agent 没有返回有效回答）"
    yield {"type": "done", "answer": answer, "trace": trace}


if __name__ == "__main__":
    import sys

    q = sys.argv[1] if len(sys.argv) > 1 else "2026年国庆节放几天假？"
    print(ask(q))
