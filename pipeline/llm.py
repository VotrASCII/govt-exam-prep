"""
LLM backend — Claude (Sonnet, high effort) via the local `claude` CLI.

Replaces the former Ollama backend. Every summary / MCQ / map-reduce / news call in the
pipeline goes through `call_llm(prompt)`. It shells out to `claude -p` so it uses the
logged-in Claude Code account (no API key needed). Note: if ANTHROPIC_API_KEY is set in the
environment the CLI bills that key instead of the subscription.

Overrides (env): PIPELINE_LLM_MODEL, PIPELINE_LLM_EFFORT, CLAUDE_TIMEOUT_SECONDS, CLAUDE_BIN.
"""

import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import (
    CLAUDE_EFFORT,
    CLAUDE_MAX_ATTEMPTS,
    CLAUDE_MODEL,
    CLAUDE_SYSTEM_PROMPT,
    CLAUDE_TIMEOUT_SECONDS,
)


def _claude_bin() -> str:
    # launchd/cron run with a minimal PATH, so also check the usual install location.
    local = Path.home() / ".local" / "bin" / "claude"
    return (
        os.getenv("CLAUDE_BIN")
        or shutil.which("claude")
        or (str(local) if local.exists() else "claude")
    )


def llm_available() -> bool:
    """True if the claude CLI is installed (auth problems surface on the first call)."""
    b = _claude_bin()
    return shutil.which(b) is not None or Path(b).exists()


def _run_claude(prompt: str, model: str, effort: str, timeout: int) -> str | None:
    cmd = [
        _claude_bin(), "-p",
        "--model", model,
        "--effort", effort,
        "--output-format", "text",
        "--tools", "",                 # pure text generation — no file/shell access
        "--system-prompt", CLAUDE_SYSTEM_PROMPT,
        "--no-session-persistence",
        "--disable-slash-commands",
    ]
    # Neutral cwd so the repo's CLAUDE.md / project settings aren't loaded into the prompt.
    with tempfile.TemporaryDirectory(prefix="claude-llm-") as cwd:
        try:
            proc = subprocess.run(
                cmd, input=prompt, capture_output=True, text=True,
                cwd=cwd, timeout=timeout,
            )
        except subprocess.TimeoutExpired:
            print(f"  [WARN] claude call timed out after {timeout}s.")
            return None
        except FileNotFoundError:
            raise RuntimeError("`claude` CLI not found. Install Claude Code and run `claude` once to log in.")
    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "").strip()[:500]
        print(f"  [WARN] claude exited {proc.returncode}: {err}")
        return None
    out = (proc.stdout or "").strip()
    if not out:
        print("  [WARN] claude returned no text.")
        return None
    return out


def call_llm(prompt: str) -> str:
    """Generate text from `prompt` with Claude Sonnet (high effort). Retries, then raises."""
    model = os.getenv("PIPELINE_LLM_MODEL", CLAUDE_MODEL)
    effort = os.getenv("PIPELINE_LLM_EFFORT", CLAUDE_EFFORT)
    timeout = int(os.getenv("CLAUDE_TIMEOUT_SECONDS", CLAUDE_TIMEOUT_SECONDS))
    for attempt in range(1, CLAUDE_MAX_ATTEMPTS + 1):
        label = "Calling" if attempt == 1 else f"Retry {attempt}/{CLAUDE_MAX_ATTEMPTS}:"
        print(f"  {label} Claude ({model}, effort={effort}) ...")
        response = _run_claude(prompt, model, effort, timeout)
        if response:
            return response
        if attempt < CLAUDE_MAX_ATTEMPTS:
            time.sleep(min(15 * attempt, 60))
    raise RuntimeError(f"Claude call failed after {CLAUDE_MAX_ATTEMPTS} attempts (model={model}).")
