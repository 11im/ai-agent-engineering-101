"""Model calls through the Claude Code CLI (`claude -p`).

Temperature is not settable through `claude -p`; it stays at the CLI default.
Each call is a fresh, tool-less session run outside the repository so that
no CLAUDE.md or project settings leak into the agent's context.
"""
import subprocess
import tempfile
import time

WORKDIR = tempfile.mkdtemp(prefix="week04-")
RETRIES = 5


def cli_version() -> str:
    out = subprocess.run(["claude", "--version"], capture_output=True, text=True)
    return out.stdout.strip()


class Model:
    def __init__(self, model: str):
        self.model = model
        self.calls = {"agent": 0, "reader": 0}

    def complete(self, system: str, user: str, kind: str = "agent") -> str:
        cmd = [
            "claude", "-p",
            "--model", self.model,
            "--system-prompt", system,
            "--tools", "",
            "--setting-sources", "",
            "--strict-mcp-config",
            "--no-session-persistence",
        ]
        last_error = ""
        for attempt in range(RETRIES):
            try:
                out = subprocess.run(cmd, input=user, capture_output=True, text=True,
                                     timeout=300, cwd=WORKDIR)
                text = out.stdout.strip()
                if out.returncode == 0 and text:
                    self.calls[kind] += 1
                    return text
                last_error = f"exit {out.returncode}: {(out.stderr or out.stdout).strip()[:200]}"
            except subprocess.TimeoutExpired:
                last_error = "timeout after 300s"
            time.sleep(5 * 2 ** attempt)
        raise RuntimeError(f"claude -p failed {RETRIES} times: {last_error}")

    def reader(self, prompt: str) -> str:
        return self.complete("You label negotiation messages. Follow the output format exactly.",
                             prompt, kind="reader")
