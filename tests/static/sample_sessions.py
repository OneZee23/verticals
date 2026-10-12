"""Sample sessions for the suite's tests of task sessions (docs/design/task-sessions.md): a home for the agents inside a
scratch folder, and Claude transcripts and Codex rollouts as they would lie in it. The sample files are made unreadable: the
gateway may stat them and may not read them, and the owner's own `~/.claude` and `~/.codex` never come into it."""

from __future__ import annotations

import importlib.util
import os
import re
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CHAT_DIR = ROOT / "desktop" / "chat"

CLAUDE_SESSION = "5f0c6a52-9d57-4c0e-9d9e-3b1f6f2f7a10"
OTHER_CLAUDE = "0b3e8a44-1b52-4f77-8c3f-6c5d2e9a1b21"
CODEX_THREAD = "0198f2c4-7b1e-7a35-b3d2-2c4e5f6a7b89"
FOLDER = "/Users/sample/Sample Project/app.v2"


def chat_module():
    """The desktop gateway's chat module, loaded by its path as the other tests of it do."""
    spec = importlib.util.spec_from_file_location("verticals_desktop_chat", CHAT_DIR / "chat.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def agent_sessions():
    sys.path.insert(0, str(CHAT_DIR))
    try:
        spec = importlib.util.spec_from_file_location("verticals_agent_sessions", CHAT_DIR / "agent_sessions.py")
        assert spec and spec.loader
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        return module
    finally:
        sys.path.remove(str(CHAT_DIR))


@contextmanager
def homes(root: Path) -> Iterator[dict[str, Path]]:
    """A home for the agents inside `root`: the files they would keep are samples here, and the owner's own never come in."""
    wanted = {"HOME": root / "home", "CLAUDE_CONFIG_DIR": root / "claude", "CODEX_HOME": root / "codex"}
    saved = {name: os.environ.get(name) for name in wanted}
    for name, path in wanted.items():
        path.mkdir(parents=True, exist_ok=True)
        os.environ[name] = str(path)
    try:
        yield wanted
    finally:
        for name, value in saved.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value


def claude_file(root: Path, folder: str, session: str, size: int = 2048, at: float | None = None,
                home: Path | None = None) -> Path:
    """A sample Claude transcript where Claude keeps it: the folder's name is the folder with every character that is not a
    letter or a digit turned into a dash (code.claude.com/docs/en/sessions, "Where transcripts are stored"). `home` is
    Claude's own home when the gateway under test keeps it somewhere other than `<root>/claude`."""
    path = (home or root / "claude") / "projects" / re.sub(r"[^a-zA-Z0-9]", "-", folder) / f"{session}.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"sample\n" * (size // 7))
    path.chmod(0)  # the gateway may stat it and may not read it
    if at is not None:
        os.utime(path, (at, at))
    return path


def codex_file(root: Path, thread: str, size: int = 4096, at: float | None = None, day: str = "2026/10/11",
               home: Path | None = None) -> Path:
    path = (home or root / "codex") / "sessions" / day / f"rollout-2026-10-11T09-30-00-{thread}.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"sample\n" * (size // 7))
    path.chmod(0)
    if at is not None:
        os.utime(path, (at, at))
    return path


def grow_file(path: Path, by: int, at: float | None = None) -> None:
    """What an agent does when a session goes on: the file is bigger and newer. Still unreadable afterwards."""
    path.chmod(0o600)
    with open(path, "ab") as grown:
        grown.write(b"sample\n" * (by // 7))
    path.chmod(0)
    if at is not None:
        os.utime(path, (at, at))
