from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

from config import ReviewerConfig
from models import ReviewDecision, SearchEvidence

AMBIGUOUS_PATTERNS = [
    r"\bmaybe\b",
    r"\bprobably\b",
    r"\bsoon\b",
    r"\bsomehow\b",
    r"会不会",
    r"大概",
    r"可能会",
    r"感觉",
    r"应该会",
]

PROHIBITED_PATTERNS = [
    r"terror",
    r"extremis",
    r"child",
    r"未成年",
    r"仇恨",
    r"种族灭绝",
    r"自杀",
    r"刺杀",
    r"暗网",
    r"毒品交易",
]

OBJECTIVE_PATTERNS = [
    r"\babove\b",
    r"\bbelow\b",
    r"\bexceed\b",
    r"\bwin\b",
    r"\blaunch\b",
    r"\bapprove\b",
    r"\bapproval\b",
    r"\blist(ed)?\b",
    r"\bannounce\b",
    r"\bconfirm\b",
    r"\bpass\b",
    r"\bpartnership\b",
    r"\bintegration\b",
    r"\brelease\b",
    r"超过",
    r"低于",
    r"达到",
    r"获批",
    r"上线",
    r"发布",
    r"赢得",
]


class ReviewerPolicy:
    def __init__(self, config: ReviewerConfig) -> None:
        self.config = config

    def evaluate(self, proposal: dict, evidence: list[SearchEvidence] | None = None) -> ReviewDecision:
        blocking_reasons: list[str] = []
        warnings: list[str] = []
        evidence = evidence or []

        title = str(proposal.get("title") or "").strip()
        description = str(proposal.get("description") or "").strip()
        full_text = f"{title}\n{description}".strip()
        close_at = datetime.fromisoformat(str(proposal["trading_close_at"]).replace("Z", "+00:00")).astimezone(timezone.utc)
        min_close = datetime.now(timezone.utc) + timedelta(seconds=self.config.reviewer_min_future_close_seconds)

        if not title or len(title) < 12:
            blocking_reasons.append("标题过短，命题表达不充分。")
        if len(title) > 180:
            warnings.append("标题较长，建议缩短以减少理解歧义。")
        if close_at <= min_close:
            blocking_reasons.append("交易截止时间过近或已过，不适合进入审核通过状态。")
        if proposal.get("yes_liquidity") != proposal.get("no_liquidity"):
            blocking_reasons.append("初始 YES/NO seed 不相等，不符合建市规则。")
        if self._matches_any(full_text, PROHIBITED_PATTERNS):
            blocking_reasons.append("命题包含常见敏感或违规内容。")
        if self._matches_any(full_text, AMBIGUOUS_PATTERNS):
            blocking_reasons.append("命题表述存在明显模糊词，结算时容易产生歧义。")
        if not self._matches_any(full_text, OBJECTIVE_PATTERNS):
            blocking_reasons.append("命题缺少可验证的客观触发条件。")
        if description and len(description) < 20:
            warnings.append("描述较短，建议补充数据口径或裁定依据。")
        if evidence:
            evidence_summary = " ; ".join(item.summary for item in evidence if item.summary)
            if evidence_summary and "未检索到可用结果" in evidence_summary:
                warnings.append("外部搜索没有拿到有效结果，建议人工复核。")

        vote = "reject" if blocking_reasons else "approve"
        summary = self._build_summary(vote, blocking_reasons, warnings, evidence)
        return ReviewDecision(
            vote=vote,
            summary=summary,
            blocking_reasons=blocking_reasons,
            warnings=warnings,
            evidence=evidence,
        )

    @staticmethod
    def should_collect_evidence(proposal: dict) -> bool:
        text = f"{proposal.get('title', '')}\n{proposal.get('description', '')}".lower()
        keywords = [
            "etf",
            "sec",
            "launch",
            "listing",
            "airdrop",
            "unlock",
            "governance",
            "proposal",
            "partnership",
            "integration",
            "release",
            "election",
            "twitter",
            "x ",
            "tesla",
            "btc",
            "eth",
            "bitcoin",
        ]
        return any(keyword in text for keyword in keywords)

    @staticmethod
    def _matches_any(text: str, patterns: list[str]) -> bool:
        return any(re.search(pattern, text, flags=re.IGNORECASE) for pattern in patterns)

    @staticmethod
    def _build_summary(
        vote: str,
        blocking_reasons: list[str],
        warnings: list[str],
        evidence: list[SearchEvidence],
    ) -> str:
        parts = [f"建议投票: {vote}。"]
        if blocking_reasons:
            parts.append("阻断原因: " + "；".join(blocking_reasons))
        if warnings:
            parts.append("提醒: " + "；".join(warnings))
        if evidence:
            parts.append("外部证据: " + "；".join(item.summary for item in evidence if item.summary))
        return " ".join(parts)
