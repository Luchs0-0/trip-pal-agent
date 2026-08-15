"""TripPal 交互式命令行入口（无 UI 时的本地使用方式）。

用法：
    python -m trip_pal.cli                 # 进入交互式多轮对话
    python -m trip_pal.cli "2026年国庆放几天假？"   # 单次问答

特性：
    - 多轮对话：保留上下文（agent 记得你之前问过什么）
    - 显示工具调用轨迹：你能看到 agent 每一步调了什么工具、参数、结果
    - 输入 exit / quit / 退出 结束
"""
from __future__ import annotations

import sys

from .graph import chat, ask_with_trace


def _print_trace(trace: list[dict]) -> None:
    """以缩进树形式打印工具调用轨迹。

    为什么截断：工具返回的 JSON 可能很长（比如全年节假日列表），
    全部打印会淹没终端；只显示参数摘要 + 结果前 120 字符，
    既能看清"调了什么工具、大致拿到什么"，又不刷屏。
    """
    if not trace:
        return
    print("\n  ┌─ Agent 工具调用过程 ─────────────────")
    for i, step in enumerate(trace, 1):
        tool = step["tool"]
        args = step["args"]
        result = step["result"]
        # 参数摘要（太长就截断）
        arg_str = ", ".join(f"{k}={v}" for k, v in args.items())
        if len(arg_str) > 80:
            arg_str = arg_str[:77] + "..."
        print(f"  │  {i}. 调用 {tool}({arg_str})")
        # 结果摘要
        result_short = result.replace("\n", " ")[:120]
        if len(result) > 120:
            result_short += "..."
        print(f"  │     → {result_short}")
    print("  └─────────────────────────────────────")


def main() -> None:
    # 单次问答模式
    if len(sys.argv) > 1:
        question = " ".join(sys.argv[1:])
        answer, trace = ask_with_trace(question)
        _print_trace(trace)
        print(f"\nTripPal: {answer}")
        return

    # 交互式多轮对话模式
    print("TripPal 交互模式已启动（输入 exit 退出）")
    print("-" * 50)
    history: list = []  # 对话历史：跨轮记忆的关键
    while True:
        try:
            question = input("你: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n再见！")
            break
        if not question:
            continue
        if question.lower() in ("exit", "quit", "退出", "q"):
            print("再见！")
            break
        try:
            # 把历史 + 新问题交给 agent，并拿回更新后的历史
            answer, trace, history = chat(history, question)
            _print_trace(trace)
            print(f"\nTripPal: {answer}\n")
        except Exception as e:  # noqa: BLE001
            print(f"\n[错误] {e}\n")


if __name__ == "__main__":
    main()
