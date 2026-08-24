"""回归测试：trace 配对（tool_call_id）与空回复兜底。"""

from types import SimpleNamespace


def _msg(obj):
    """给 SimpleNamespace 补 type 属性访问。"""
    return obj


def _mk_ai_tool_calls(calls):
    return SimpleNamespace(
        type="ai",
        tool_calls=calls,
        content="",
    )


def _mk_tool(call_id, name, content):
    return SimpleNamespace(
        type="tool",
        tool_call_id=call_id,
        name=name,
        content=content,
    )


def test_same_tool_twice_results_paired_by_id():
    """同工具连续调用两次：结果必须按 tool_call_id 配对，不能错位。"""
    # 模拟 LangGraph 返回：两个 get_holidays_cn 调用（2026 与 2027）
    messages = [
        SimpleNamespace(type="human", content="香港圣诞怎么拼假"),
        _mk_ai_tool_calls(
            [
                {"name": "suggest_leave_stacking", "args": {"year": 2026}, "id": "call_aaa"},
                {"name": "suggest_leave_stacking", "args": {"year": 2027}, "id": "call_bbb"},
            ]
        ),
        # 结果故意乱序返回：bbb 先回，aaa 后回
        _mk_tool("call_bbb", "suggest_leave_stacking", "RESULT_2027"),
        _mk_tool("call_aaa", "suggest_leave_stacking", "RESULT_2026"),
        SimpleNamespace(type="ai", content="最终回答", tool_calls=None),
    ]
    agent = SimpleNamespace(invoke=lambda payload: {"messages": messages})

    import trip_pal.graph as g

    orig = g.build_agent
    g.build_agent = lambda: agent
    try:
        answer, trace = g.ask_with_trace("香港圣诞怎么拼假")
    finally:
        g.build_agent = orig

    by_args = {t["args"]["year"]: t["result"] for t in trace}
    assert by_args[2026] == "RESULT_2026", f"2026 结果错位: {trace}"
    assert by_args[2027] == "RESULT_2027", f"2027 结果错位: {trace}"
    assert answer == "最终回答"


def test_empty_reply_fallback():
    """模型返回空内容时：answer 用兜底文案，不再是旧占位符。"""
    messages = [
        SimpleNamespace(type="human", content="hi"),
        SimpleNamespace(type="ai", content="", tool_calls=None),
    ]
    agent = SimpleNamespace(invoke=lambda payload: {"messages": messages})

    import trip_pal.graph as g

    orig = g.build_agent
    g.build_agent = lambda: agent
    try:
        answer, _trace, _hist = g.chat([], "hi")
    finally:
        g.build_agent = orig

    assert answer == "（Agent 未能生成回答，请重试或换个问法）"
    assert "没有返回有效回答" not in answer
