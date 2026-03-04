"""
AI client — calls Claude via the Claude Code CLI subprocess.
Requires Claude Code CLI installed and authenticated on the server.
"""

import logging
import os
import subprocess
from config import NVM_BIN, SYSTEM_PROMPT

log = logging.getLogger(__name__)


def call_ai(messages: list[dict], system_prompt: str = "") -> str | None:
    """
    Call Claude CLI with a conversation history.

    Args:
        messages: List of {"role": "user"|"assistant", "content": str}
        system_prompt: Override system prompt (falls back to config default)

    Returns:
        Response text, or None on failure.
    """
    sys_prompt = system_prompt or SYSTEM_PROMPT

    # Flatten history into a single prompt
    history = ""
    for msg in messages[:-1]:
        role = "User" if msg["role"] == "user" else "Assistant"
        history += f"{role}: {msg['content']}\n"
    last = messages[-1]["content"]
    prompt = f"{sys_prompt}\n\n{history}User: {last}\n\nRespond:" if history else f"{sys_prompt}\n\n{last}"

    env = os.environ.copy()
    env.pop("CLAUDECODE", None)
    env["HOME"] = os.path.expanduser("~")
    env["PATH"] = f"{NVM_BIN}:{env.get('PATH', '/usr/local/bin:/usr/bin:/bin')}"

    try:
        result = subprocess.run(
            ["claude", "-p", prompt, "--allowedTools", "WebSearch,WebFetch"],
            capture_output=True, text=True, timeout=180, env=env,
        )
        if result.returncode != 0 or not result.stdout.strip():
            log.error(f"Claude CLI error (rc={result.returncode}): {result.stderr.strip()[:200]}")
            return None
        return result.stdout.strip()
    except Exception as e:
        log.error(f"Claude CLI exception: {e}")
        return None
