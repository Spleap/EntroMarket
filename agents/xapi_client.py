from __future__ import annotations

import json
import os
import subprocess
import sys

from models import SearchEvidence


class XApiClient:
    def __init__(self, enabled: bool, api_key: str | None, timeout_seconds: int = 25) -> None:
        self.enabled = enabled and bool(api_key)
        self.api_key = api_key
        self.timeout_seconds = timeout_seconds

    def search_news(self, query: str) -> SearchEvidence | None:
        if not self.enabled:
            return None

        payload = self._call("web.search.news", {"q": query})
        summary = self._summarize_payload(payload)
        return SearchEvidence(provider="xapi", query=query, summary=summary, raw=payload)

    def web_search(self, query: str) -> SearchEvidence | None:
        if not self.enabled:
            return None

        payload = self._call("web.search.realtime", {"q": query, "timeRange": "day"})
        summary = self._summarize_payload(payload)
        return SearchEvidence(provider="xapi", query=query, summary=summary, raw=payload)

    def token_price(self, token: str, chain: str = "eth") -> SearchEvidence | None:
        if not self.enabled:
            return None

        payload = self._call("crypto.token.price", {"token": token, "chain": chain})
        summary = self._summarize_price_payload(token, payload)
        return SearchEvidence(provider="xapi", query=f"{token} price on {chain}", summary=summary, raw=payload)

    def twitter_search(self, raw_query: str, sort_by: str = "Latest", provider: str = "x") -> dict | list:
        return self._call(
            "twitter.search",
            {
                "raw_query": raw_query,
                "sort_by": sort_by,
                "provider": provider,
            },
        )

    def _call(self, api_id: str, payload: dict) -> dict | list:
        if not self.enabled:
            raise RuntimeError("xAPI is not enabled")

        env = os.environ.copy()
        env["XAPI_KEY"] = self.api_key or ""
        executable = "npx.cmd" if sys.platform.startswith("win") else "npx"
        command = [
            executable,
            "--yes",
            "xapi-to",
            "call",
            api_id,
            "--input",
            json.dumps(payload, ensure_ascii=False),
            "--format",
            "json",
        ]
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=self.timeout_seconds,
            encoding="utf-8",
            errors="replace",
            env=env,
        )
        if completed.returncode != 0:
            raise RuntimeError(completed.stderr.strip() or completed.stdout.strip() or "xAPI search failed")
        return json.loads(completed.stdout)

    @staticmethod
    def _summarize_price_payload(token: str, payload: dict | list) -> str:
        if isinstance(payload, dict):
            data = payload.get("data", payload)
            if isinstance(data, dict):
                price = data.get("price") or data.get("usd") or data.get("value")
                change = data.get("change24h") or data.get("change_24h") or data.get("change")
                return f"{token} current price={price}, 24h change={change}"
        return f"{token} price payload received"

    @staticmethod
    def _summarize_payload(payload: dict | list) -> str:
        if isinstance(payload, list):
            items = payload
        else:
            data = payload.get("data", payload)
            if isinstance(data, dict):
                items = (
                    data.get("news")
                    or data.get("items")
                    or data.get("results")
                    or payload.get("items")
                    or payload.get("results")
                    or []
                )
            else:
                items = payload.get("items") or payload.get("results") or data or []
        if not isinstance(items, list) or not items:
            return "xAPI 未检索到可用结果。"

        snippets: list[str] = []
        for item in items[:3]:
            if not isinstance(item, dict):
                continue
            title = str(item.get("title") or item.get("name") or "").strip()
            source = str(item.get("source") or item.get("site") or item.get("domain") or "").strip()
            if title:
                snippets.append(f"{title} ({source or 'unknown'})")
        return " ; ".join(snippets) if snippets else json.dumps(payload, ensure_ascii=False)[:500]
