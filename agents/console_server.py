from __future__ import annotations

import argparse
from collections import deque
import json
import mimetypes
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from config import load_config


ROLE_FILES = {
    "reviewer": "reviewer_log_path",
    "resolver": "resolver_log_path",
    "proposer": "proposer_log_path",
    "trader": "trader_log_path",
}

HISTORY_ARCHIVE_FILE = "dashboard_history.jsonl"
HISTORY_OFFSETS_FILE = "dashboard_history_offsets.json"

ROLE_WALLET_SPECS = {
    "reviewer": {
        "wallets_file": "reviewer_wallets_file",
        "wallet_start": "reviewer_wallet_start",
        "wallet_count": "reviewer_wallet_count",
    },
    "resolver": {
        "wallets_file": "reviewer_wallets_file",
        "wallet_start": "resolver_wallet_start",
        "wallet_count": "resolver_wallet_count",
    },
    "proposer": {
        "wallets_file": "participant_wallets_file",
        "wallet_start": "proposer_wallet_start",
        "wallet_count": "proposer_wallet_count",
    },
    "trader": {
        "wallets_file": "participant_wallets_file",
        "wallet_start": "trader_wallet_start",
        "wallet_count": "trader_wallet_count",
    },
}


@dataclass(slots=True)
class ConsoleContext:
    base_dir: Path
    log_paths: dict[str, Path]
    state_dir: Path
    configured_agents_by_role: dict[str, list[dict[str, str]]]
    history_path: Path
    history_offsets_path: Path


def build_context() -> ConsoleContext:
    config = load_config()
    return ConsoleContext(
        base_dir=Path(__file__).resolve().parent,
        log_paths={role: Path(getattr(config, attr)) for role, attr in ROLE_FILES.items()},
        state_dir=Path(__file__).resolve().parent / "state",
        configured_agents_by_role=load_configured_agents_by_role(config),
        history_path=(Path(__file__).resolve().parent / "state" / HISTORY_ARCHIVE_FILE),
        history_offsets_path=(Path(__file__).resolve().parent / "state" / HISTORY_OFFSETS_FILE),
    )


class ConsoleHandler(BaseHTTPRequestHandler):
    server_version = "EntroConsole/0.1"
    context: ConsoleContext | None = None

    @classmethod
    def _get_context(cls) -> ConsoleContext:
        if cls.context is None:
            cls.context = build_context()
        return cls.context

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path == "/api/overview":
            return self._handle_overview()
        if parsed.path == "/api/events":
            return self._handle_events(parsed.query)
        if parsed.path == "/api/history":
            return self._handle_history(parsed.query)
        if parsed.path == "/api/workspace":
            return self._handle_workspace()
        if parsed.path == "/api/stream":
            return self._handle_stream(parsed.query)
        return self._handle_static(parsed.path)

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A003
        return

    def _handle_overview(self) -> None:
        context = self._get_context()
        sync_history_archive(context)
        roles = []
        all_observed_agent_names: set[str] = set()
        all_live_agent_names: set[str] = set()
        latest_timestamps: list[str] = []
        now = datetime.now(timezone.utc)
        for role, path in context.log_paths.items():
            events = load_recent_events(path, role, limit=80)
            configured_agents = context.configured_agents_by_role.get(role, [])
            configured_agent_names = [item["agent_name"] for item in configured_agents]
            last_timestamp = events[0]["timestamp"] if events else None
            is_live = False
            if last_timestamp:
                parsed = parse_timestamp(last_timestamp)
                if parsed is not None:
                    is_live = (now - parsed).total_seconds() <= 180
                    latest_timestamps.append(last_timestamp)
            observed_agent_names = sorted({str(item.get("agent_name") or role) for item in events})
            live_agent_names = sorted(
                {
                    str(item.get("agent_name") or role)
                    for item in events
                    if is_recent_timestamp(item.get("timestamp"), now=now)
                }
            )
            all_observed_agent_names.update(observed_agent_names)
            all_live_agent_names.update(live_agent_names)
            roles.append(
                {
                    "role": role,
                    "file_path": str(path),
                    "exists": path.exists(),
                    "event_count": len(events),
                    "last_timestamp": last_timestamp,
                    "live": is_live,
                    "configured_agent_count": len(configured_agents),
                    "configured_agent_names": configured_agent_names,
                    "observed_agent_count": len(observed_agent_names),
                    "observed_agent_names": observed_agent_names,
                    "live_agent_count": len(live_agent_names),
                    "live_agent_names": live_agent_names,
                }
            )

        recent_events = load_history_events(context, role="all", limit=96, offset=0)
        configured_agents = [
            {"role": role, **item}
            for role, items in context.configured_agents_by_role.items()
            for item in items
        ]
        workspace_files = [
            {
                "name": item.name,
                "path": str(item),
                "kind": "dir" if item.is_dir() else "file",
            }
            for item in sorted(context.base_dir.iterdir(), key=lambda entry: entry.name.lower())
            if item.name not in {"__pycache__", "web", ".env"}
        ]
        payload = {
            "summary": {
                "configured_agent_total": len(configured_agents),
                "configured_agents": configured_agents,
                "observed_agent_total": len(all_observed_agent_names),
                "observed_agent_names": sorted(all_observed_agent_names),
                "live_agent_total": len(all_live_agent_names),
                "live_agent_names": sorted(all_live_agent_names),
                "latest_timestamp": max(latest_timestamps) if latest_timestamps else (recent_events[0]["timestamp"] if recent_events else None),
            },
            "roles": roles,
            "recent_events": recent_events,
            "workspace_files": workspace_files,
        }
        self._json_response(payload)

    def _handle_events(self, query_string: str) -> None:
        context = self._get_context()
        params = parse_qs(query_string)
        role = params.get("role", ["all"])[0]
        requested_limit = int(params.get("limit", ["200"])[0])
        limit = max(1, min(requested_limit, 800))
        events: list[dict[str, Any]] = []
        for selected_role in expand_roles(role):
            path = context.log_paths[selected_role]
            events.extend(load_recent_events(path, selected_role, limit=limit))
        events = sorted(events, key=lambda item: item.get("timestamp", ""), reverse=True)[:limit]
        self._json_response({"events": events})

    def _handle_history(self, query_string: str) -> None:
        context = self._get_context()
        params = parse_qs(query_string)
        role = params.get("role", ["all"])[0]
        requested_limit = int(params.get("limit", ["200"])[0])
        limit = max(1, min(requested_limit, 800))
        requested_offset = int(params.get("offset", ["0"])[0])
        offset = max(0, requested_offset)
        sync_history_archive(context)
        total = count_history_events(context, role=role)
        events = load_history_events(context, role=role, limit=limit, offset=offset)
        next_offset = offset + len(events)
        payload = {
            "events": events,
            "offset": offset,
            "limit": limit,
            "total": total,
            "has_more": next_offset < total,
            "next_offset": next_offset if next_offset < total else None,
            "archive_path": str(context.history_path),
        }
        self._json_response(payload)

    def _handle_workspace(self) -> None:
        context = self._get_context()
        items = []
        for target in [context.base_dir / "logs", context.base_dir / "state"]:
            if not target.exists():
                continue
            for item in sorted(target.iterdir(), key=lambda entry: entry.name.lower()):
                items.append(
                    {
                        "name": item.name,
                        "path": str(item),
                        "kind": "dir" if item.is_dir() else "file",
                        "size": item.stat().st_size if item.is_file() else None,
                    }
                )
        self._json_response({"items": items})

    def _handle_stream(self, query_string: str) -> None:
        context = self._get_context()
        params = parse_qs(query_string)
        role = params.get("role", ["all"])[0]
        selected_roles = expand_roles(role)
        offsets = {item: file_size(context.log_paths[item]) for item in selected_roles}

        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self._set_cors_headers()
        self.end_headers()

        try:
            while True:
                emitted = False
                for selected_role in selected_roles:
                    path = context.log_paths[selected_role]
                    offset = offsets[selected_role]
                    for next_offset, event in iter_new_events(path, selected_role, offset):
                        offsets[selected_role] = next_offset
                        self.wfile.write(f"data: {json.dumps(event, ensure_ascii=False)}\n\n".encode("utf-8"))
                        self.wfile.flush()
                        emitted = True
                if not emitted:
                    self.wfile.write(b": ping\n\n")
                    self.wfile.flush()
                time.sleep(1.0)
        except (BrokenPipeError, ConnectionResetError):
            return

    def _json_response(self, payload: dict[str, Any], status: HTTPStatus = HTTPStatus.OK) -> None:
        body = json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self._set_cors_headers()
        self.end_headers()
        self.wfile.write(body)

    def _handle_static(self, request_path: str) -> None:
        context = self._get_context()
        dist_dir = context.base_dir / "web" / "dist"
        if not dist_dir.exists():
            self._json_response({"detail": "Not found"}, status=HTTPStatus.NOT_FOUND)
            return

        relative = request_path.lstrip("/") or "index.html"
        target = (dist_dir / relative).resolve()
        if not str(target).startswith(str(dist_dir.resolve())):
            self._json_response({"detail": "Not found"}, status=HTTPStatus.NOT_FOUND)
            return
        if target.is_dir():
            target = target / "index.html"
        if not target.exists():
            target = dist_dir / "index.html"

        body = target.read_bytes()
        mime_type, _ = mimetypes.guess_type(str(target))
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", mime_type or "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _set_cors_headers(self) -> None:
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")


def expand_roles(role: str) -> list[str]:
    if role == "all":
        return list(ROLE_FILES.keys())
    if role not in ROLE_FILES:
        return list(ROLE_FILES.keys())
    return [role]


def file_size(path: Path) -> int:
    if not path.exists():
        return 0
    return path.stat().st_size


def load_events(path: Path, role: str) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    events = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            raw = json.loads(line)
        except json.JSONDecodeError:
            continue
        events.append(normalize_event(raw, role))
    return events


def load_recent_events(path: Path, role: str, *, limit: int) -> list[dict[str, Any]]:
    if not path.exists() or limit <= 0:
        return []
    raw_items = read_jsonl_tail(path, max_lines=limit)
    events = [normalize_event(raw, role) for raw in raw_items]
    return sorted(events, key=lambda item: item.get("timestamp", ""), reverse=True)


def sync_history_archive(context: ConsoleContext) -> None:
    context.state_dir.mkdir(parents=True, exist_ok=True)
    offsets = load_history_offsets(context.history_offsets_path)
    seen_ids = load_history_ids(context.history_path) if context.history_path.exists() and not context.history_offsets_path.exists() else set()
    archived_events: list[dict[str, Any]] = []

    for role, path in context.log_paths.items():
        current_size = file_size(path)
        start_offset = int(offsets.get(role, 0))
        if start_offset > current_size:
            start_offset = 0
        events = iter_new_events(path, role, start_offset)
        if not events:
            offsets[role] = current_size
            continue
        for next_offset, event in events:
            offsets[role] = next_offset
            if not is_dashboard_relevant_event(event):
                continue
            if event["id"] in seen_ids:
                continue
            seen_ids.add(event["id"])
            archived_events.append(event)

    if archived_events:
        archived_events.sort(key=lambda item: item.get("timestamp", ""))
        with context.history_path.open("a", encoding="utf-8") as handle:
            for event in archived_events:
                handle.write(json.dumps(event, ensure_ascii=False) + "\n")

    save_history_offsets(context.history_offsets_path, offsets)


def load_history_events(context: ConsoleContext, *, role: str, limit: int, offset: int) -> list[dict[str, Any]]:
    events = [
        item
        for item in load_archive_events(context.history_path)
        if role == "all" or item.get("role") == role
    ]
    events.sort(key=lambda item: item.get("timestamp", ""), reverse=True)
    return events[offset : offset + limit]


def count_history_events(context: ConsoleContext, *, role: str) -> int:
    if role == "all":
        return len(load_archive_events(context.history_path))
    return sum(1 for item in load_archive_events(context.history_path) if item.get("role") == role)


def load_archive_events(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    output: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            raw = json.loads(line)
        except json.JSONDecodeError:
            continue
        if is_archive_event(raw):
            output.append(raw)
    return output


def load_history_ids(path: Path) -> set[str]:
    return {str(item.get("id")) for item in load_archive_events(path) if item.get("id")}


def load_history_offsets(path: Path) -> dict[str, int]:
    if not path.exists():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    if not isinstance(raw, dict):
        return {}
    output: dict[str, int] = {}
    for role, value in raw.items():
        try:
            output[str(role)] = int(value)
        except (TypeError, ValueError):
            continue
    return output


def save_history_offsets(path: Path, offsets: dict[str, int]) -> None:
    path.write_text(json.dumps(offsets, ensure_ascii=False, indent=2), encoding="utf-8")


def read_jsonl_tail(path: Path, *, max_lines: int) -> list[dict[str, Any]]:
    if max_lines <= 0 or not path.exists():
        return []

    lines: deque[bytes] = deque(maxlen=max_lines)
    with path.open("rb") as handle:
        handle.seek(0, 2)
        file_size_bytes = handle.tell()
        block_size = 8192
        remainder = b""
        position = file_size_bytes

        while position > 0 and len(lines) < max_lines:
            read_size = min(block_size, position)
            position -= read_size
            handle.seek(position)
            chunk = handle.read(read_size)
            data = chunk + remainder
            parts = data.split(b"\n")
            remainder = parts[0]
            for line in reversed(parts[1:]):
                stripped = line.strip()
                if stripped:
                    lines.appendleft(stripped)
                    if len(lines) >= max_lines:
                        break

        if remainder.strip() and len(lines) < max_lines:
            lines.appendleft(remainder.strip())

    output: list[dict[str, Any]] = []
    for raw_line in list(lines)[-max_lines:]:
        try:
            output.append(json.loads(raw_line.decode("utf-8", errors="replace")))
        except json.JSONDecodeError:
            continue
    return output


def iter_new_events(path: Path, role: str, offset: int) -> list[tuple[int, dict[str, Any]]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        handle.seek(offset)
        output: list[tuple[int, dict[str, Any]]] = []
        while True:
            line = handle.readline()
            if not line:
                break
            next_offset = handle.tell()
            line = line.strip()
            if not line:
                continue
            try:
                raw = json.loads(line)
            except json.JSONDecodeError:
                continue
            output.append((next_offset, normalize_event(raw, role)))
        return output


def as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def format_probability_percent(value: Any) -> str | None:
    try:
        return f"{float(value) * 100:.2f}%"
    except (TypeError, ValueError):
        return None


def normalize_event(raw: dict[str, Any], role: str) -> dict[str, Any]:
    if "event_type" in raw:
        return {
            "id": build_event_id(raw, role),
            "timestamp": raw.get("timestamp"),
            "role": raw.get("role") or role,
            "agent_name": raw.get("agent_name") or role,
            "event_type": raw.get("event_type"),
            "content": raw.get("content") or "",
            "payload": raw.get("payload"),
            "title": raw.get("event_type"),
        }

    agent_name = str(raw.get("agent_name") or role)
    timestamp = raw.get("timestamp")
    if "vote" in raw and role == "reviewer":
        content = f"{agent_name} 对提案投了 {raw.get('vote')}。{raw.get('summary') or ''}".strip()
        event_type = "decision"
        title = raw.get("proposal_title") or raw.get("proposal_id") or "review"
    elif raw.get("action") == "create_resolution_proposal":
        content = f"{agent_name} 创建了 resolution proposal，outcome={raw.get('proposed_outcome')}。"
        event_type = "action"
        title = raw.get("market_title") or raw.get("market_id") or "resolution"
    elif "vote" in raw and role == "resolver":
        content = f"{agent_name} 对结算提案投了 {raw.get('vote')}。{raw.get('rationale') or ''}".strip()
        event_type = "decision"
        title = raw.get("market_title") or raw.get("proposal_id") or "resolution"
    elif raw.get("action") == "submit_market_review_proposal":
        auth_text = "使用签名 API 提交命题"
        content = f"{agent_name} {auth_text}：{raw.get('proposal_title')} (tweet {raw.get('tweet_id')})"
        event_type = "action"
        title = raw.get("proposal_title") or "proposal"
    elif raw.get("action") == "query_probability":
        result = as_dict(raw.get("payload"))
        probability_text = format_probability_percent(result.get("probability_yes"))
        fee_text = result.get("entropy_fee_charged")
        if probability_text:
            content = f"{agent_name} 使用签名 API 查询了实时概率：YES {probability_text}"
            if fee_text is not None:
                content += f"，消耗 {fee_text} ENTROPY"
            content += f"。 -> {raw.get('api_path')}"
        else:
            content = f"{agent_name} 通过签名 API 执行了 query_probability -> {raw.get('api_path')}"
        event_type = "action"
        title = raw.get("market_title") or raw.get("market_id") or "probability"
    elif raw.get("action") == "skip_candidate":
        content = f"跳过 tweet {raw.get('tweet_id')}，query={raw.get('query')}"
        event_type = "thought"
        title = raw.get("query") or "candidate"
    elif raw.get("action") in {"buy_yes", "buy_no", "sell_yes", "sell_no", "add_liquidity_yes", "add_liquidity_no", "settle"}:
        result = as_dict(raw.get("payload"))
        trade = as_dict(result.get("trade"))
        side = trade.get("side") or raw.get("action")
        share_delta = trade.get("share_delta")
        probability_after = format_probability_percent(trade.get("probability_yes_after"))
        total_amount = trade.get("total_amount")
        content = f"{agent_name} 通过签名 API 执行了 {side}"
        if share_delta is not None:
            content += f"，份额变化 {share_delta}"
        if total_amount is not None:
            content += f"，成交金额 {total_amount}"
        if probability_after:
            content += f"，执行后 YES 概率 {probability_after}"
        content += f"。 -> {raw.get('api_path')}"
        event_type = "action"
        title = raw.get("market_title") or raw.get("market_id") or str(raw.get("action"))
    elif raw.get("action"):
        if role in {"proposer", "trader"} and raw.get("auth_mode") == "eip712_signed_api":
            content = f"{agent_name} 通过签名 API 执行了 {raw.get('action')} -> {raw.get('api_path')}"
        else:
            content = f"{agent_name} 执行了 {raw.get('action')}"
        event_type = "action"
        title = raw.get("market_title") or raw.get("action")
    else:
        content = json.dumps(raw, ensure_ascii=False, default=str)[:400]
        event_type = "tool_result"
        title = role

    return {
        "id": build_event_id(raw, role),
        "timestamp": timestamp,
        "role": role,
        "agent_name": agent_name,
        "event_type": event_type,
        "content": content,
        "payload": raw,
        "title": title,
    }


def build_event_id(raw: dict[str, Any], role: str) -> str:
    timestamp = raw.get("timestamp") or time.time()
    primary = raw.get("proposal_id") or raw.get("market_id") or raw.get("tweet_id") or raw.get("account_id") or "event"
    kind = raw.get("event_type") or raw.get("action") or "event"
    agent_name = raw.get("agent_name") or role
    return f"{role}:{agent_name}:{kind}:{primary}:{timestamp}"


def parse_timestamp(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone(timezone.utc)
    except ValueError:
        return None


def is_recent_timestamp(value: str | None, *, now: datetime, window_seconds: int = 180) -> bool:
    parsed = parse_timestamp(value)
    if parsed is None:
        return False
    return (now - parsed).total_seconds() <= window_seconds


def is_dashboard_relevant_event(event: dict[str, Any]) -> bool:
    role = str(event.get("role") or "")
    event_type = str(event.get("event_type") or "")
    payload = as_dict(event.get("payload"))
    action = str(payload.get("action") or "")

    if role == "proposer":
        return event_type == "action" and action == "submit_market_review_proposal"
    if role in {"reviewer", "resolver"}:
        return event_type == "decision"
    if role == "trader":
        return event_type == "action" and action in {
            "query_probability",
            "buy_yes",
            "buy_no",
            "sell_yes",
            "sell_no",
            "add_liquidity",
            "add_liquidity_yes",
            "add_liquidity_no",
            "settle",
        }
    return False


def is_archive_event(value: Any) -> bool:
    if not isinstance(value, dict):
        return False
    return (
        isinstance(value.get("id"), str)
        and isinstance(value.get("role"), str)
        and isinstance(value.get("agent_name"), str)
        and isinstance(value.get("event_type"), str)
        and isinstance(value.get("content"), str)
    )


def load_configured_agents_by_role(config: Any) -> dict[str, list[dict[str, str]]]:
    output: dict[str, list[dict[str, str]]] = {}
    for role, spec in ROLE_WALLET_SPECS.items():
        output[role] = load_wallet_slice(
            Path(getattr(config, spec["wallets_file"])),
            start=int(getattr(config, spec["wallet_start"])),
            count=int(getattr(config, spec["wallet_count"])),
        )
    return output


def load_wallet_slice(path: Path, *, start: int, count: int) -> list[dict[str, str]]:
    if not path.exists():
        return []
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []
    start_index = max(start - 1, 0)
    selected = raw[start_index : start_index + max(count, 0)]
    output: list[dict[str, str]] = []
    for item in selected:
        output.append(
            {
                "agent_name": str(item.get("agent_name") or ""),
                "address": str(item.get("address") or "").lower(),
            }
        )
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description="Local dashboard API for EntroMarket agents.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()

    server = ThreadingHTTPServer((args.host, args.port), ConsoleHandler)
    print(f"[console] serving agent dashboard API at http://{args.host}:{args.port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("[console] stopped", flush=True)


if __name__ == "__main__":
    main()
