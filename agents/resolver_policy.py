from __future__ import annotations

import json
import re

from deepseek_client import DeepSeekClient
from models import ResolutionAssessment, SearchEvidence
from xapi_client import XApiClient


PRICE_PATTERNS = [
    re.compile(r"\b(ETH|BTC)\b.*\babove\s+(\d+(?:\.\d+)?)", re.IGNORECASE),
    re.compile(r"\b(ETH|BTC)\b.*\bbelow\s+(\d+(?:\.\d+)?)", re.IGNORECASE),
]


class ResolverPolicy:
    def __init__(self, xapi_client: XApiClient, deepseek_client: DeepSeekClient) -> None:
        self.xapi_client = xapi_client
        self.deepseek_client = deepseek_client

    def assess_market(self, market: dict) -> ResolutionAssessment:
        title = str(market.get("title") or "")
        description = str(market.get("description") or "")
        evidence: list[SearchEvidence] = []

        price_assessment = self._assess_price_market(title, evidence)
        if price_assessment is not None:
            return price_assessment

        if self.xapi_client.enabled:
            for query in self._search_queries(title, description):
                try:
                    result = self.xapi_client.search_news(query)
                    if result is not None:
                        evidence.append(result)
                except Exception:
                    continue

        llm_result = self._assess_with_llm(market, evidence)
        if llm_result is not None:
            return llm_result

        return ResolutionAssessment(
            proposed_outcome="no",
            vote="veto",
            rationale="缺少足够可验证证据，默认否决当前结算提案，等待人工或后续 fallback。",
            confidence=0.2,
            evidence=evidence,
        )

    def vote_for_proposal(self, market: dict, proposal: dict) -> ResolutionAssessment:
        independent = self.assess_market(market)
        expected_vote = "no_veto" if independent.proposed_outcome == proposal["proposed_outcome"] else "veto"
        rationale = (
            f"独立判断 outcome={independent.proposed_outcome}，提案 outcome={proposal['proposed_outcome']}，"
            f"因此投 {expected_vote}。 {independent.rationale}"
        )
        return ResolutionAssessment(
            proposed_outcome=independent.proposed_outcome,
            vote=expected_vote,
            rationale=rationale,
            confidence=independent.confidence,
            evidence=independent.evidence,
        )

    def _assess_price_market(self, title: str, evidence: list[SearchEvidence]) -> ResolutionAssessment | None:
        normalized = title.strip()
        for pattern in PRICE_PATTERNS:
            match = pattern.search(normalized)
            if not match:
                continue
            token = match.group(1).upper()
            threshold = float(match.group(2))
            direction = "above" if "above" in match.group(0).lower() else "below"
            if not self.xapi_client.enabled:
                break
            price_evidence = self.xapi_client.token_price(token, chain="eth")
            if price_evidence is None:
                break
            evidence.append(price_evidence)
            current_price = self._extract_numeric_price(price_evidence.raw)
            if current_price is None:
                break
            is_yes = current_price > threshold if direction == "above" else current_price < threshold
            return ResolutionAssessment(
                proposed_outcome="yes" if is_yes else "no",
                vote="no_veto",
                rationale=(
                    f"根据 xAPI 抓取到的 {token} 实时价格 {current_price}，"
                    f"对照阈值 {threshold} 得出 outcome={'yes' if is_yes else 'no'}。"
                ),
                confidence=0.9,
                evidence=evidence,
            )
        return None

    def _assess_with_llm(self, market: dict, evidence: list[SearchEvidence]) -> ResolutionAssessment | None:
        if not self.deepseek_client.enabled:
            return None

        system_prompt = (
            "You are a prediction market resolver. "
            "Return strict JSON with keys: proposed_outcome, vote, confidence, rationale. "
            "proposed_outcome must be yes or no. "
            "vote must be no_veto when the evidence is sufficient and the outcome is clear, otherwise veto."
        )
        evidence_text = "\n".join(f"- {item.summary}" for item in evidence) or "- no external evidence"
        user_prompt = (
            f"Market title: {market.get('title')}\n"
            f"Market description: {market.get('description')}\n"
            f"Trading close at: {market.get('trading_close_at')}\n"
            f"Collected evidence:\n{evidence_text}\n"
            "Decide the most defensible market outcome and whether a resolution proposal for that outcome should be vetoed."
        )
        payload = self.deepseek_client.json_completion(system_prompt, user_prompt)
        if not payload:
            return None
        outcome = str(payload.get("proposed_outcome", "no")).strip().lower()
        vote = str(payload.get("vote", "veto")).strip().lower()
        confidence = float(payload.get("confidence", 0.5))
        rationale = str(payload.get("rationale") or json.dumps(payload, ensure_ascii=False))
        if outcome not in {"yes", "no"}:
            outcome = "no"
        if vote not in {"veto", "no_veto"}:
            vote = "veto"
        return ResolutionAssessment(
            proposed_outcome=outcome,
            vote=vote,
            rationale=rationale,
            confidence=max(0.0, min(confidence, 1.0)),
            evidence=evidence,
        )

    @staticmethod
    def _extract_numeric_price(payload: dict | list | None) -> float | None:
        if isinstance(payload, dict):
            data = payload.get("data", payload)
            if isinstance(data, dict):
                price = data.get("price") or data.get("usd") or data.get("value")
                try:
                    return float(price)
                except (TypeError, ValueError):
                    return None
        return None

    @staticmethod
    def _search_queries(title: str, description: str) -> list[str]:
        base = title.strip()
        if description:
            return [base, f"{base} {description[:120]}"]
        return [base]
