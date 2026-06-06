from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from typing import Any

from deepseek_client import DeepSeekClient
from models import ProposalDraft

GENERIC_QUERY_WORDS = {
    "announcement",
    "announce",
    "approval",
    "approved",
    "airdrop",
    "binance",
    "coinbase",
    "crypto",
    "decision",
    "etf",
    "launch",
    "listing",
    "mainnet",
    "polling",
    "proposal",
    "rate",
    "release",
    "sec",
    "snapshot",
    "stablecoin",
    "testnet",
    "token",
    "unlock",
    "upbit",
    "kraken",
}


@dataclass(slots=True)
class TweetCandidate:
    query: str
    tweet_id: str
    text: str
    created_at: datetime
    author: str
    followers_count: int
    favorite_count: int
    reply_count: int
    retweet_count: int
    view_count: int
    raw: dict[str, Any]


class ProposerPolicy:
    def __init__(
        self,
        deepseek_client: DeepSeekClient,
        default_close_minutes: int,
        default_seed_liquidity: str,
    ) -> None:
        self.deepseek_client = deepseek_client
        self.default_close_minutes = default_close_minutes
        self.default_seed_liquidity = default_seed_liquidity

    def extract_candidates(self, query: str, payload: dict | list) -> list[TweetCandidate]:
        tweets = []
        if isinstance(payload, dict):
            data = payload.get("data", {})
            if isinstance(data, dict):
                tweets = data.get("tweets") or []
        candidates: list[TweetCandidate] = []
        for item in tweets:
            if not isinstance(item, dict):
                continue
            if item.get("is_reply") or item.get("is_retweet"):
                continue
            created_at = self._parse_datetime(item.get("created_at"))
            if created_at is None or created_at < datetime.now(timezone.utc) - timedelta(hours=24):
                continue
            user = item.get("user") or {}
            followers_count = int(user.get("followers_count") or 0)
            favorite_count = int(item.get("favorite_count") or 0)
            reply_count = int(item.get("reply_count") or 0)
            retweet_count = int(item.get("retweet_count") or 0)
            engagement = favorite_count + reply_count + retweet_count
            if followers_count < 80 or engagement < 1:
                continue
            text = str(item.get("text") or "").strip()
            if len(text) < 24:
                continue
            candidates.append(
                TweetCandidate(
                    query=query,
                    tweet_id=str(item.get("tweet_id")),
                    text=text,
                    created_at=created_at,
                    author=str(user.get("screen_name") or user.get("name") or "unknown"),
                    followers_count=followers_count,
                    favorite_count=favorite_count,
                    reply_count=reply_count,
                    retweet_count=retweet_count,
                    view_count=int(item.get("view_count") or 0),
                    raw=item,
                )
            )
        candidates.sort(
            key=lambda item: (item.followers_count, item.favorite_count + item.reply_count + item.retweet_count, item.view_count),
            reverse=True,
        )
        return candidates

    def build_proposal(self, candidate: TweetCandidate) -> ProposalDraft | None:
        if not self.deepseek_client.enabled:
            return self._fallback_event_or_price_market(candidate)

        system_prompt = (
            "You are a proposer for a prediction market. "
            "Return strict JSON with keys: should_propose, title, description, category, tags, "
            "trading_close_minutes, rationale. "
            "Only propose objective, clearly resolvable, future-looking binary markets. "
            "Prefer diverse event-driven markets over repetitive BTC/ETH price thresholds. "
            "You may transform a credible current signal into a short-horizon follow-on market "
            "such as approval by deadline, listing by deadline, launch by deadline, release by deadline, "
            "governance pass/fail by deadline, partnership announcement by deadline, or price above/below a concrete threshold as a last resort. "
            "Reject rumors, pure commentary, price opinions without a measurable threshold, and vague narratives."
        )
        user_prompt = (
            f"Source query: {candidate.query}\n"
            f"Tweet id: {candidate.tweet_id}\n"
            f"Author: @{candidate.author}\n"
            f"Followers: {candidate.followers_count}\n"
            f"Engagement: favorites={candidate.favorite_count}, replies={candidate.reply_count}, retweets={candidate.retweet_count}, views={candidate.view_count}\n"
            f"Created at: {candidate.created_at.isoformat()}\n"
            f"Tweet text:\n{candidate.text}\n"
            "Generate a market review proposal only if the event can be resolved by public reporting within hours or days. "
            "It is acceptable to derive a forward-looking market from the tweet's signal if the resulting market is still objective and measurable. "
            "Prefer non-price event markets whenever possible. "
            "Use concise English title. trading_close_minutes should be between 60 and 1440."
        )
        payload = self.deepseek_client.json_completion(system_prompt, user_prompt)
        if not payload:
            return self._fallback_event_or_price_market(candidate)
        should_propose = bool(payload.get("should_propose"))
        if not should_propose:
            return self._fallback_event_or_price_market(candidate)

        title = str(payload.get("title") or "").strip()
        description = str(payload.get("description") or "").strip()
        category = str(payload.get("category") or "crypto").strip() or "crypto"
        tags = payload.get("tags") or ["xapi", "x", "agent"]
        if not isinstance(tags, list):
            tags = ["xapi", "x", "agent"]
        tags = [str(tag).strip().lower()[:24] for tag in tags if str(tag).strip()][:5]
        if "xapi" not in tags:
            tags.append("xapi")
        trading_close_minutes = int(payload.get("trading_close_minutes") or self.default_close_minutes)
        trading_close_minutes = max(60, min(trading_close_minutes, 1440))
        rationale = str(payload.get("rationale") or "").strip()

        if not title or len(title) < 16:
            return None
        if not description:
            description = (
                f"Generated from X signal @{candidate.author} / tweet {candidate.tweet_id}. "
                "The reviewer agents should verify the claim is objective and publicly resolvable."
            )
        return ProposalDraft(
            source_tweet_id=candidate.tweet_id,
            source_query=candidate.query,
            title=title[:180],
            description=description,
            category=category,
            tags=tags,
            trading_close_minutes=trading_close_minutes,
            yes_liquidity=self.default_seed_liquidity,
            no_liquidity=self.default_seed_liquidity,
            rationale=rationale or json.dumps(payload, ensure_ascii=False),
        )

    def _fallback_event_or_price_market(self, candidate: TweetCandidate) -> ProposalDraft | None:
        event_market = self._fallback_event_market(candidate)
        if event_market is not None:
            return event_market
        return self._fallback_price_market(candidate)

    def _fallback_event_market(self, candidate: TweetCandidate) -> ProposalDraft | None:
        text = candidate.text.lower()
        subject = self._extract_subject(candidate)
        category = "news"
        event_kind = ""
        title = ""
        description = ""
        tags = ["xapi", "x", "signal"]

        if any(keyword in text for keyword in ["listing", "listed", "binance", "coinbase", "upbit", "kraken"]):
            event_kind = "listing"
            category = "exchange"
            title = f"Will {subject} announce a new exchange listing by market close?"
            description = (
                f"Generated from X signal query '{candidate.query}' based on tweet {candidate.tweet_id}. "
                f"Market resolves YES if a credible public listing announcement for {subject} appears before market close."
            )
            tags.extend(["listing", "exchange"])
        elif any(keyword in text for keyword in ["mainnet", "testnet", "launch", "deploy", "deployment"]):
            event_kind = "launch"
            category = "launch"
            title = f"Will {subject} announce a launch milestone by market close?"
            description = (
                f"Generated from X signal query '{candidate.query}' based on tweet {candidate.tweet_id}. "
                f"Market resolves YES if {subject} publicly confirms a launch milestone before market close."
            )
            tags.extend(["launch", "product"])
        elif any(keyword in text for keyword in ["airdrop", "snapshot", "claim"]):
            event_kind = "airdrop"
            category = "airdrop"
            title = f"Will {subject} confirm an airdrop update by market close?"
            description = (
                f"Generated from X signal query '{candidate.query}' based on tweet {candidate.tweet_id}. "
                f"Market resolves YES if {subject} publicly confirms an airdrop, snapshot, or claim update before market close."
            )
            tags.extend(["airdrop", "distribution"])
        elif any(keyword in text for keyword in ["unlock", "vesting", "cliff"]):
            event_kind = "unlock"
            category = "tokenomics"
            title = f"Will {subject} announce a token unlock update by market close?"
            description = (
                f"Generated from X signal query '{candidate.query}' based on tweet {candidate.tweet_id}. "
                f"Market resolves YES if {subject} publicly confirms a token unlock-related update before market close."
            )
            tags.extend(["unlock", "tokenomics"])
        elif any(keyword in text for keyword in ["approve", "approval", "etf", "sec"]):
            event_kind = "approval"
            category = "regulation"
            title = f"Will {subject} receive an approval headline by market close?"
            description = (
                f"Generated from X signal query '{candidate.query}' based on tweet {candidate.tweet_id}. "
                f"Market resolves YES if a credible approval or regulatory headline for {subject} appears before market close."
            )
            tags.extend(["approval", "regulation"])
        elif any(keyword in text for keyword in ["vote", "proposal", "dao", "governance"]):
            event_kind = "governance"
            category = "governance"
            title = f"Will {subject} governance proposal pass by market close?"
            description = (
                f"Generated from X signal query '{candidate.query}' based on tweet {candidate.tweet_id}. "
                f"Market resolves YES if a public governance proposal outcome for {subject} is confirmed as passed before market close."
            )
            tags.extend(["governance", "vote"])
        elif any(keyword in text for keyword in ["partnership", "partner", "integration", "integrates", "support"]):
            event_kind = "partnership"
            category = "adoption"
            title = f"Will {subject} announce a partnership update by market close?"
            description = (
                f"Generated from X signal query '{candidate.query}' based on tweet {candidate.tweet_id}. "
                f"Market resolves YES if {subject} publicly announces a partnership or integration update before market close."
            )
            tags.extend(["partnership", "adoption"])
        elif any(keyword in text for keyword in ["release", "ship", "rollout", "update", "feature"]):
            event_kind = "release"
            category = "product"
            title = f"Will {subject} release a product update by market close?"
            description = (
                f"Generated from X signal query '{candidate.query}' based on tweet {candidate.tweet_id}. "
                f"Market resolves YES if {subject} publicly releases or confirms a product update before market close."
            )
            tags.extend(["release", "product"])

        if not event_kind:
            return None

        return ProposalDraft(
            source_tweet_id=candidate.tweet_id,
            source_query=candidate.query,
            title=title,
            description=description,
            category=category,
            tags=self._normalize_tags(tags + self._query_tags(candidate.query)),
            trading_close_minutes=self.default_close_minutes,
            yes_liquidity=self.default_seed_liquidity,
            no_liquidity=self.default_seed_liquidity,
            rationale=(
                f"Fallback {event_kind} market derived from tweet {candidate.tweet_id} "
                f"under query '{candidate.query}' with subject '{subject}'."
            ),
        )

    def _fallback_price_market(self, candidate: TweetCandidate) -> ProposalDraft | None:
        parsed = self._extract_price_signal(candidate.text)
        if parsed is None:
            return None
        symbol, price = parsed
        direction = self._infer_price_direction(candidate.text)
        threshold = self._derive_price_threshold(price, direction)
        threshold_label = self._format_price_label(threshold)
        title = f"Will {symbol} trade {direction} {threshold_label} by market close?"
        description = (
            f"Generated from X signal query '{candidate.query}' based on tweet {candidate.tweet_id}. "
            f"Observed {symbol} reference price around {price:.2f}. "
            f"Market resolves YES if {symbol} trades {direction} {threshold_label} at market close using public market data."
        )
        return ProposalDraft(
            source_tweet_id=candidate.tweet_id,
            source_query=candidate.query,
            title=title,
            description=description,
            category="crypto",
            tags=["xapi", "x", symbol.lower(), "signal"],
            trading_close_minutes=self.default_close_minutes,
            yes_liquidity=self.default_seed_liquidity,
            no_liquidity=self.default_seed_liquidity,
            rationale=(
                f"Fallback price-signal market derived from tweet mentioning {symbol} around {price:.2f}, "
                f"with a {direction} threshold at {threshold_label}."
            ),
        )

    @staticmethod
    def _normalize_tags(tags: list[str]) -> list[str]:
        normalized: list[str] = []
        for tag in tags:
            clean = str(tag).strip().lower().replace(" ", "-")[:24]
            if clean and clean not in normalized:
                normalized.append(clean)
        return normalized[:5]

    @staticmethod
    def _query_tags(query: str) -> list[str]:
        return [part.strip().lower() for part in query.split() if part.strip()][:3]

    def _extract_subject(self, candidate: TweetCandidate) -> str:
        ticker_match = re.search(r"\$([A-Za-z][A-Za-z0-9]{1,9})", candidate.text)
        if ticker_match:
            return ticker_match.group(1).upper()

        uppercase_match = re.search(r"\b([A-Z]{2,8})\b", candidate.text)
        if uppercase_match and uppercase_match.group(1).lower() not in GENERIC_QUERY_WORDS:
            return uppercase_match.group(1)

        capitalized_match = re.search(r"\b([A-Z][a-zA-Z0-9]{2,20})\b", candidate.text)
        if capitalized_match:
            return capitalized_match.group(1)

        for part in re.split(r"[\s,/]+", candidate.query):
            clean = part.strip().lower()
            if clean and clean not in GENERIC_QUERY_WORDS:
                return part.strip().title()
        return "the project"

    @staticmethod
    def _parse_datetime(value: Any) -> datetime | None:
        if not value:
            return None
        if isinstance(value, str):
            try:
                return parsedate_to_datetime(value).astimezone(timezone.utc)
            except (TypeError, ValueError):
                return None
        return None

    @staticmethod
    def _extract_price_signal(text: str) -> tuple[str, float] | None:
        normalized = text.replace(",", "")
        patterns = [
            re.compile(r"\b(BTC|ETH)\s*\$([0-9]+(?:\.[0-9]+)?)", re.IGNORECASE),
            re.compile(r"\b(Bitcoin|Ethereum)[^$]{0,30}\$([0-9]+(?:\.[0-9]+)?)", re.IGNORECASE),
        ]
        for pattern in patterns:
            match = pattern.search(normalized)
            if not match:
                continue
            symbol = match.group(1).upper()
            if symbol == "BITCOIN":
                symbol = "BTC"
            if symbol == "ETHEREUM":
                symbol = "ETH"
            return symbol, float(match.group(2))
        return None

    @staticmethod
    def _infer_price_direction(text: str) -> str:
        lowered = text.lower()
        bearish_markers = [
            "falls below",
            "fell below",
            "drops below",
            "dropped below",
            "below",
            "selloff",
            "outflow",
            "outflows",
            "liquidation",
            "bearish",
            "slump",
            "plunge",
            "dump",
            "decline",
        ]
        bullish_markers = [
            "breaks above",
            "broke above",
            "surges above",
            "surged above",
            "above",
            "inflow",
            "inflows",
            "bullish",
            "rally",
            "soar",
            "jump",
            "gain",
            "approval",
            "listing",
            "launch",
        ]
        bearish_score = sum(1 for marker in bearish_markers if marker in lowered)
        bullish_score = sum(1 for marker in bullish_markers if marker in lowered)
        return "below" if bearish_score > bullish_score else "above"

    @staticmethod
    def _derive_price_threshold(price: float, direction: str) -> float:
        step = ProposerPolicy._price_step(price)
        move = max(step, price * 0.02)
        raw_target = price - move if direction == "below" else price + move
        if direction == "below":
            target = (raw_target // step) * step
            if target >= price:
                target -= step
        else:
            target = ((raw_target + step - 1e-9) // step) * step
            if target <= price:
                target += step
        return max(step, float(target))

    @staticmethod
    def _price_step(price: float) -> float:
        if price >= 50000:
            return 1000
        if price >= 10000:
            return 500
        if price >= 1000:
            return 100
        if price >= 100:
            return 10
        if price >= 10:
            return 1
        if price >= 1:
            return 0.1
        return 0.01

    @staticmethod
    def _format_price_label(value: float) -> str:
        if value >= 1000 and value.is_integer():
            return f"${int(value):,}"
        if value >= 1:
            return f"${value:,.2f}".rstrip("0").rstrip(".")
        return f"${value:.4f}".rstrip("0").rstrip(".")
