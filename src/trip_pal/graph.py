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

    这是「多轮记忆」的核心函数：
      - history: 之前的完整对话消息列表（LangChain 消息对象）
      - question: 用户刚输入的新问题
      - 返回的第三个值 history_new：把本轮对话追加进去，下次再传回来即可

    调用方（CLI / Web）负责保存 history_new，实现跨轮记忆。
    """
    agent = build_agent()
    # 把历史 + 新问题拼在一起发给 agent —— 这就是记忆的机制
    messages_in = list(history) + [{"role": "user", "content": question}]
    result = agent.invoke({"messages": messages_in})
    messages = result.get("messages", [])

    # 提取回答 + 工具轨迹（逻辑与 ask_with_trace 相同）
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

    # 更新后的历史 = 完整消息（包含本轮新增的所有消息）
    history_new = messages
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

    # 遍历完整消息历史，区分三类消息：
    #   1) ai + tool_calls   → 模型"要求调用工具"（记录到 trace）
    #   2) tool              → 工具执行结果（回填到 trace 对应项）
    #   3) ai + 无 tool_calls → 模型的最终回答
    trace: list[dict] = []
    answer = "（Agent 没有返回有效回答）"
    for msg in messages:
        mtype = getattr(msg, "type", "")
        if mtype == "ai" and getattr(msg, "tool_calls", None):
            # 模型可能一次请求调用多个工具，逐个记录
            for tc in msg.tool_calls:
                trace.append(
                    {
                        "tool": tc.get("name", ""),
                        "args": tc.get("args", {}),
                        "result": "（等待执行）",
                    }
                )
        elif mtype == "tool":
            # 工具结果消息带 name（哪个工具）和 content（返回内容）。
            # 用 reversed 从后往前找"同名且尚未回填"的 trace 项，
            # 因为同一个工具可能被调用多次，要回填到最近那一次。
            for item in reversed(trace):
                if item["tool"] == msg.name and item["result"] == "（等待执行）":
                    item["result"] = str(msg.content)[:500]
                    break
        elif mtype == "ai" and not getattr(msg, "tool_calls", None):
            # 不带 tool_calls 的 AI 消息 = 最终回答（循环终止）
            answer = str(msg.content)
    return answer, trace


if __name__ == "__main__":
    import sys

    q = sys.argv[1] if len(sys.argv) > 1 else "2026年国庆节放几天假？"
    print(ask(q))
