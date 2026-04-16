import functools
from pathlib import Path

PROMPT_DIR = Path(__file__).parent.parent / "prompts"


@functools.lru_cache(maxsize=1)
def load_system_prompt() -> str:
    return (PROMPT_DIR / "system_prompt.txt").read_text(encoding="utf-8")
