from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from deepseek_client import DeepSeekClient
from models import AgentTraceEvent


class RuntimeTool:
    def __init__(
        self,
        name: str,
        description: str,
        handler: Callable[[dict[str, Any]], Any],
        summarize: Callable[[Any], str] | None = None,
    ) -> None:
        self.name = name
        self.description = description
        self.handler = handler
        self.summarize = summarize or self._default_summary

    @staticmethod
    def _default_summary(result: Any) -> str:
        if result is None:
            return "No result."
        if isinstance(result, (str, int, float, bool)):
            return str(result)
        if isinstance(result, list):
            return f"Returned list with {len(result)} item(s)."
        if isinstance(result, dict):
            keys = ", ".join(sorted(result.keys())[:8])
            return f"Returned object with keys: {keys}"
        return str(result)


class AgentTraceLogger:
    def __init__(self, role: str, agent_name: str, log_path: Path) -> None:
        self.role = role
        self.agent_name = agent_name
        self.log_path = log_path
        self.log_path.parent.mkdir(parents=True, exist_ok=True)

    def emit(self, event_type: str, content: str, payload: dict | list | None = None) -> None:
        event = AgentTraceEvent(
            role=self.role,
            agent_name=self.agent_name,
            event_type=event_type,
            content=content,
            payload=payload,
        )
        line = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            **asdict(event),
        }
        with self.log_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(line, ensure_ascii=False, default=str) + "\n")
        print(f"[{self.role}:{self.agent_name}] {event_type}: {content}", flush=True)


class ChatStyleToolAgent:
    def __init__(
        self,
        *,
        role: str,
        agent_name: str,
        deepseek_client: DeepSeekClient,
        logger: AgentTraceLogger,
        max_steps: int = 6,
    ) -> None:
        self.role = role
        self.agent_name = agent_name
        self.deepseek_client = deepseek_client
        self.logger = logger
        self.max_steps = max_steps

    def run(
        self,
        *,
        task: str,
        context: dict[str, Any],
        tools: list[RuntimeTool],
        fallback: Callable[[], dict[str, Any]],
        system_prompt: str,
    ) -> dict[str, Any]:
        tool_map = {tool.name: tool for tool in tools}
        history: list[dict[str, Any]] = []
        self.logger.emit("task", task, {"context": context})

        if not self.deepseek_client.enabled:
            self.logger.emit("fallback", "DeepSeek is disabled, using deterministic fallback.")
            result = fallback()
            self.logger.emit("final", "Fallback completed.", result)
            return result

        for step in range(1, self.max_steps + 1):
            #region debug-point runtime-model-request-start
            self.logger.emit("status", "debug: runtime model request started", {"step": step})
            #endregion
            try:
                payload = self.deepseek_client.json_completion(
                    system_prompt=system_prompt,
                    user_prompt=self._build_user_prompt(task=task, context=context, tools=tools, history=history),
                )
            except Exception as exc:
                #region debug-point runtime-model-request-error
                self.logger.emit("status", "debug: runtime model request failed", {"step": step, "error": str(exc)})
                #endregion
                raise
            #region debug-point runtime-model-request-finished
            self.logger.emit(
                "status",
                "debug: runtime model request finished",
                {"step": step, "has_payload": bool(payload)},
            )
            #endregion
            if not payload:
                break

            thought = str(payload.get("thought") or "").strip()
            if thought:
                self.logger.emit("thought", thought, {"step": step})
                history.append({"type": "thought", "content": thought})

            final = payload.get("final")
            if isinstance(final, dict) and final:
                self.logger.emit("final", "Agent produced final output.", final)
                return final

            tool_name = str(payload.get("tool_name") or "").strip()
            tool_input = payload.get("tool_input")
            if not tool_name:
                break
            if tool_name not in tool_map:
                message = f"Unknown tool '{tool_name}'."
                self.logger.emit("tool_error", message, {"step": step})
                history.append({"type": "tool_error", "tool_name": tool_name, "content": message})
                continue
            if not isinstance(tool_input, dict):
                tool_input = {}

            tool = tool_map[tool_name]
            self.logger.emit(
                "tool_call",
                f"{tool_name}({json.dumps(tool_input, ensure_ascii=False)})",
                {"step": step, "tool_name": tool_name, "tool_input": tool_input},
            )
            try:
                result = tool.handler(tool_input)
            except Exception as exc:
                error_message = f"{tool_name} failed: {exc}"
                self.logger.emit(
                    "tool_error",
                    error_message,
                    {"step": step, "tool_name": tool_name, "tool_input": tool_input},
                )
                history.append({"type": "tool_error", "tool_name": tool_name, "content": error_message})
                continue

            summary = tool.summarize(result)
            self.logger.emit("tool_result", summary, {"step": step, "tool_name": tool_name, "result": result})
            history.append(
                {
                    "type": "tool_result",
                    "tool_name": tool_name,
                    "tool_input": tool_input,
                    "summary": summary,
                    "result": result,
                }
            )

        self.logger.emit("fallback", "Agent did not finish within step budget, using deterministic fallback.")
        result = fallback()
        self.logger.emit("final", "Fallback completed.", result)
        return result

    @staticmethod
    def _build_user_prompt(
        *,
        task: str,
        context: dict[str, Any],
        tools: list[RuntimeTool],
        history: list[dict[str, Any]],
    ) -> str:
        tool_text = "\n".join(f"- {tool.name}: {tool.description}" for tool in tools)
        history_text = json.dumps(history, ensure_ascii=False, indent=2, default=str)
        context_text = json.dumps(context, ensure_ascii=False, indent=2, default=str)
        return (
            f"Task:\n{task}\n\n"
            f"Current context:\n{context_text}\n\n"
            f"Available tools:\n{tool_text}\n\n"
            f"Interaction history:\n{history_text}\n\n"
            "Return strict JSON with keys: thought, tool_name, tool_input, final.\n"
            "- Choose exactly one tool call per turn, or provide final.\n"
            "- final should be an object only when the task is complete.\n"
            "- Keep thought concise but explicit about the next step.\n"
        )
