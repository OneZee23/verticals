"""Environment contract — docs/IMPLEMENTATION.md §6.3, frozen there and invented nowhere else.

Every variable this process reads lives here and only here. A transport calls `load()` once at
boot and passes the resulting `Config` down; nothing else under `verticals/` reads `os.environ`
directly. (The migration runner is the one pre-existing exception: `verticals/db/runner.py`
shipped in an earlier work package and reads `VERTICALS_DATABASE_URL` itself, before this module
existed — not this module's file to change.)

`VERTICALS_OWNER` is deliberately not required and defaults to `local`, not a real name (§6.3's
own note: a required variable with a default is a contradiction the boot check cannot
implement). `core/` never reads this value at all — every `core/` callable takes `owner`
explicitly, with no default (AC-013) — so this module only carries it for whichever transport
wants it.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

# S-113: the container entrypoint writes a real token on first run, mode 0600, printed once.
# The process itself never generates one — a placeholder left in place must fail boot, not
# quietly authenticate every request that shows up carrying it.
_PLACEHOLDER_TOKEN = "REPLACE_ME_THIS_VALUE_NEVER_AUTHENTICATES"

_DEFAULT_OWNER = "local"
_DEFAULT_BIND = "127.0.0.1:8080"
_DEFAULT_MCP_BIND = "127.0.0.1:8081"
_DEFAULT_POOL_MIN = 2
_DEFAULT_POOL_MAX = 10
_DEFAULT_LOG_LEVEL = "info"
_DEFAULT_SOURCES_TICK = 60.0


class ConfigError(RuntimeError):
    """A required variable is missing, empty, or (for the token) still the shipped
    placeholder. Boot-time only — not one of `core/errors.py`'s IR-03 taxonomy, since nothing
    has accepted a request yet for a transport to map."""


@dataclass(frozen=True)
class Config:
    database_url: str
    token: str
    owner: str
    bind: str
    mcp_bind: str
    pool_min: int
    pool_max: int
    log_level: str
    # Sources (docs/design/sources.md): seconds between the timer's looks at what is due (0 turns it off), and the agent
    # CLIs whose MCP servers it asks which answer (today only "claude"; none by default, so a test never reaches one).
    sources_tick: float = _DEFAULT_SOURCES_TICK
    connections: tuple[str, ...] = ()


def _require(name: str) -> str:
    value = os.environ.get(name, "")
    if not value:
        raise ConfigError(f"{name} is required and must be a non-empty value")
    return value


def _optional(name: str, default: str) -> str:
    value = os.environ.get(name)
    return value if value else default


def _optional_int(name: str, default: int) -> int:
    value = os.environ.get(name)
    if not value:
        return default
    try:
        return int(value)
    except ValueError:
        raise ConfigError(f"{name} must be an integer, got {value!r}") from None


def _optional_float(name: str, default: float) -> float:
    value = os.environ.get(name)
    if not value:
        return default
    try:
        return float(value)
    except ValueError:
        raise ConfigError(f"{name} must be a number, got {value!r}") from None


def load() -> Config:
    """Read and validate the whole `.env` contract in one pass. Raises `ConfigError` naming
    the offending variable; never returns a partially-valid `Config`.

    `load_dotenv()` is a documented no-op when no `.env` file is found (the container sets
    real environment variables and ships no `.env`), so calling it unconditionally is safe in
    every environment this runs in.
    """
    load_dotenv()

    database_url = _require("VERTICALS_DATABASE_URL")

    token = os.environ.get("VERTICALS_TOKEN", "")
    if not token or token == _PLACEHOLDER_TOKEN:
        raise ConfigError(
            "VERTICALS_TOKEN is required and must not be the shipped placeholder "
            f"({_PLACEHOLDER_TOKEN!r}); the container entrypoint generates a real one on "
            "first run"
        )

    pool_min = _optional_int("VERTICALS_POOL_MIN", _DEFAULT_POOL_MIN)
    pool_max = _optional_int("VERTICALS_POOL_MAX", _DEFAULT_POOL_MAX)
    if pool_min < 1:
        raise ConfigError(f"VERTICALS_POOL_MIN must be >= 1, got {pool_min}")
    if pool_max < pool_min:
        raise ConfigError(
            f"VERTICALS_POOL_MAX ({pool_max}) must be >= VERTICALS_POOL_MIN ({pool_min})"
        )

    sources_tick = _optional_float("VERTICALS_SOURCES_TICK", _DEFAULT_SOURCES_TICK)
    if sources_tick < 0:
        raise ConfigError(f"VERTICALS_SOURCES_TICK must be 0 (off) or a number of seconds, got {sources_tick}")
    connections = tuple(
        name.strip().lower() for name in _optional("VERTICALS_CONNECTIONS", "").split(",") if name.strip()
    )

    return Config(
        database_url=database_url,
        token=token,
        owner=_optional("VERTICALS_OWNER", _DEFAULT_OWNER),
        bind=_optional("VERTICALS_BIND", _DEFAULT_BIND),
        mcp_bind=_optional("VERTICALS_MCP_BIND", _DEFAULT_MCP_BIND),
        pool_min=pool_min,
        pool_max=pool_max,
        log_level=_optional("VERTICALS_LOG_LEVEL", _DEFAULT_LOG_LEVEL),
        sources_tick=sources_tick,
        connections=connections,
    )
