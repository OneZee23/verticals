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
from urllib.parse import urlparse

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
_LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1"}


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
    # The desktop app's loopback address, which the app hands this server as an argument, not through the environment contract:
    # where the sessions of tasks are kept (docs/design/task-sessions.md). Empty anywhere else.
    gateway_url: str = ""


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


def parse_gateway_url(value: str) -> str:
    """The desktop app's address as the server was given it: empty, or `http://<loopback host>:<port>`. This server tells that
    address which task a session belongs to, and sends nothing to any other."""
    if not value:
        return ""
    parsed = urlparse(value)
    try:
        port = parsed.port
    except ValueError:
        port = None
    if parsed.scheme != "http" or parsed.hostname not in _LOOPBACK_HOSTS or port is None:
        raise ConfigError(f"--gateway-url must be 'http://127.0.0.1:<port>' (a loopback address), got {value!r}")
    return value.rstrip("/")


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

    return Config(
        database_url=database_url,
        token=token,
        owner=_optional("VERTICALS_OWNER", _DEFAULT_OWNER),
        bind=_optional("VERTICALS_BIND", _DEFAULT_BIND),
        mcp_bind=_optional("VERTICALS_MCP_BIND", _DEFAULT_MCP_BIND),
        pool_min=pool_min,
        pool_max=pool_max,
        log_level=_optional("VERTICALS_LOG_LEVEL", _DEFAULT_LOG_LEVEL),
    )
