"""Shared plumbing for the specialist sub-agents.

Every expert runs `run_expert`, a manual tool loop over Claude (Opus 4.8) with two tools:
  - web_search  — Anthropic server tool for current 2026 facts (prices, schedules, availability)
  - query_graph — the graphify knowledge graph built from the scraped travel blogs/guides

This is how requirement #5 ("all agents should have access to graphify") is satisfied: the
graph tool is wired into the shared runner, so hotel / transport / budget experts all get it.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys

import anthropic

from trip_planner.config import settings

MODEL = "claude-opus-4-8"
GRAPH_PATH = "data/graphify-out/graph.json"  # built by scripts/build_graph.py (graphify)

WEB_SEARCH_TOOL = {"type": "web_search_20260209", "name": "web_search"}
QUERY_GRAPH_TOOL = {
    "name": "query_graph",
    "description": (
        "Query the knowledge graph graphify built over the scraped travel sources "
        "(blogs and guides) — discover how places, neighborhoods, foods, and routes connect."
    ),
    "input_schema": {
        "type": "object",
        "properties": {"question": {"type": "string"}},
        "required": ["question"],
        "additionalProperties": False,
    },
}

aclient = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key or "missing")


async def query_graph(question: str) -> str:
    """Run a graphify query as a subprocess and return its answer text."""
    if not os.path.exists(GRAPH_PATH):
        return "The knowledge graph isn't built yet (run scripts/build_graph.py)."
    proc = await asyncio.create_subprocess_exec(
        sys.executable, "-m", "graphify", "query", question,
        "--graph", GRAPH_PATH, "--budget", "1200",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        out, err = await asyncio.wait_for(proc.communicate(), timeout=60)
    except TimeoutError:
        proc.kill()
        return "Graph query timed out."
    text = out.decode("utf-8", "replace").strip() or err.decode("utf-8", "replace").strip()
    return text[:6000] or "(no graph result)"


def _extract_balanced(text: str, open_ch: str, close_ch: str) -> str | None:
    start = text.find(open_ch)
    if start == -1:
        return None
    depth = 0
    in_str = False
    esc = False
    for i in range(start, len(text)):
        ch = text[i]
        if esc:
            esc = False
            continue
        if ch == "\\":
            esc = True
            continue
        if ch == '"':
            in_str = not in_str
            continue
        if in_str:
            continue
        if ch == open_ch:
            depth += 1
        elif ch == close_ch:
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
    return None


def extract_json_object(text: str) -> dict:
    """Return the first balanced {...} JSON object in `text`, or {} if none parses."""
    raw = _extract_balanced(text, "{", "}")
    if not raw:
        return {}
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return value if isinstance(value, dict) else {}


async def run_expert(*, system: str, user: str, max_iters: int = 8) -> str:
    """Run a specialist sub-agent loop with web_search + query_graph; return its final text."""
    messages: list[dict] = [{"role": "user", "content": user}]
    tools = [WEB_SEARCH_TOOL, QUERY_GRAPH_TOOL]
    final_text = ""
    for _ in range(max_iters):
        resp = await aclient.messages.create(
            model=MODEL,
            max_tokens=4000,
            system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
            messages=messages,
            tools=tools,
        )
        text = "".join(b.text for b in resp.content if b.type == "text")
        if text:
            final_text = text
        if resp.stop_reason == "end_turn":
            break
        if resp.stop_reason == "pause_turn":
            messages.append({"role": "assistant", "content": resp.content})
            continue
        messages.append({"role": "assistant", "content": resp.content})
        results = []
        for block in resp.content:
            if block.type == "tool_use" and block.name == "query_graph":
                out = await query_graph(dict(block.input).get("question", ""))
                results.append({"type": "tool_result", "tool_use_id": block.id, "content": out})
        if not results:
            break
        messages.append({"role": "user", "content": results})
    return final_text
