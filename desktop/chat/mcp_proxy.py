#!/usr/bin/env python3
"""Stdio MCP server for agents that take MCP servers as commands (Codex): relays every
JSON-RPC message to the demo's streamable-HTTP MCP endpoint. The URL comes from the environment
(VERTICALS_MCP_URL), never from arguments, and so does the bearer token (VERTICALS_MCP_TOKEN) for the
Codex the gateway starts itself. A Codex the owner connected from the menu bar ("Use Verticals in
Codex") is given the path of the owner-only file the launcher writes instead (VERTICALS_MCP_HEADERS):
the token is read from it at every message, so it is in no Codex setting and a new launch's token is
the one used."""
import json
import os
import sys
import urllib.error
import urllib.request

URL = os.environ["VERTICALS_MCP_URL"]
HEADERS_FILE = os.environ.get("VERTICALS_MCP_HEADERS")
if not (os.environ.get("VERTICALS_MCP_TOKEN") or HEADERS_FILE):
    sys.exit("VERTICALS_MCP_TOKEN or VERTICALS_MCP_HEADERS is needed")
session_id = None


def authorization():
    token = os.environ.get("VERTICALS_MCP_TOKEN")
    if token:
        return f"Bearer {token}"
    with open(HEADERS_FILE) as f:
        return str(json.load(f)["Authorization"])


def emit(message):
    sys.stdout.write(json.dumps(message) + "\n")
    sys.stdout.flush()


def relay(message):
    global session_id
    headers = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream",
               "Authorization": authorization()}
    if session_id:
        headers["Mcp-Session-Id"] = session_id
    req = urllib.request.Request(URL, data=json.dumps(message).encode(), headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=600) as resp:
        session_id = resp.headers.get("Mcp-Session-Id") or session_id
        if resp.status == 202:
            return
        body = resp.read().decode("utf-8", "replace")
        if "text/event-stream" in (resp.headers.get("Content-Type") or ""):
            # One JSON-RPC message per SSE `data:` block.
            for block in body.split("\n\n"):
                data = "\n".join(line[5:].lstrip() for line in block.splitlines() if line.startswith("data:"))
                if data:
                    emit(json.loads(data))
        elif body.strip():
            emit(json.loads(body))


for line in sys.stdin:
    line = line.strip()
    if not line:
        continue
    try:
        message = json.loads(line)
    except ValueError:
        continue
    try:
        relay(message)
    except (OSError, urllib.error.HTTPError, ValueError, KeyError) as e:
        if isinstance(message, dict) and "id" in message and "method" in message:
            emit({"jsonrpc": "2.0", "id": message["id"],
                  "error": {"code": -32000, "message": f"Verticals MCP unavailable: {e}"}})
