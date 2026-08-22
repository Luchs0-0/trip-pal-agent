"""配置管理：模型、数据路径、运行参数。

模型认证（按优先级）：
  1. .env / 环境变量中的 OPENAI_API_KEY；
  2. 自动从 opencode 本地认证文件读取 Go 订阅 key
     （~/.local/share/opencode/auth.json 的 opencode-go.key），
     已登录 opencode Go 订阅的用户无需额外配置。
"""

from __future__ import annotations

import json
from pathlib import Path

from dotenv import load_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _load_env() -> None:
    env_file = PROJECT_ROOT / ".env"
    if env_file.exists():
        load_dotenv(env_file)


_load_env()


def _opencode_go_key() -> str:
    """从 opencode 本地认证文件读取 Go 订阅 key（若存在）。"""
    auth_path = Path.home() / ".local" / "share" / "opencode" / "auth.json"
    try:
        data = json.loads(auth_path.read_text(encoding="utf-8"))
        key = data.get("opencode-go", {}).get("key", "")
        if key:
            return key
    except (OSError, ValueError):
        pass
    return ""


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # ---- 模型（OpenCode Go 订阅 · OpenAI 兼容）----
    # 端点: https://opencode.ai/zen/go/v1 （OpenAI 兼容）
    # 模型: deepseek-v4-flash（DeepSeek V4 Flash）
    openai_api_key: str = ""
    openai_base_url: str = "https://opencode.ai/zen/go/v1"
    model: str = "deepseek-v4-flash"
    temperature: float = 0.1

    # ---- 数据 ----
    data_dir: Path = PROJECT_ROOT / "data"

    # ---- 运行 ----
    max_agent_steps: int = 10  # 防止 agent 无限循环的安全阀

    def resolved_api_key(self) -> str:
        """最终使用的 API key：优先 .env 显式配置，否则读 opencode auth。"""
        if self.openai_api_key:
            return self.openai_api_key
        return _opencode_go_key()


def get_settings() -> Settings:
    return Settings()


settings = get_settings()
