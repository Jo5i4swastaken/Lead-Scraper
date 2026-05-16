from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from lead_scraper.models import Lead
from lead_scraper.scorers.base import BaseScorer


@dataclass(frozen=True, slots=True)
class LeadQualityScorerConfig:
    low_reviews_threshold: int = 20
    inactive_social_days_threshold: int = 90
    min_social_links_for_presence: int = 1

    weights: dict[str, float] = None  # type: ignore[assignment]
    qualified_threshold: float = 50.0

    @staticmethod
    def defaults_weights() -> dict[str, float]:
        return {
            "no_website_listed": 25.0,
            "no_website_verified": 15.0,
            "low_reviews": 15.0,
            "incomplete_profile": 10.0,
            "weak_presence": 20.0,
            "inactive_social": 15.0,
        }

    @classmethod
    def from_settings_dict(cls, settings: object | None) -> "LeadQualityScorerConfig":
        raw = settings if isinstance(settings, dict) else {}
        weights_raw = raw.get("weights") if isinstance(raw, dict) else None
        weights: dict[str, float] = cls.defaults_weights()
        if isinstance(weights_raw, dict):
            for k, v in weights_raw.items():
                try:
                    weights[str(k)] = float(v)
                except Exception:
                    continue

        return cls(
            low_reviews_threshold=int(raw.get("low_reviews_threshold", cls.low_reviews_threshold)),
            inactive_social_days_threshold=int(
                raw.get("inactive_social_days_threshold", cls.inactive_social_days_threshold)
            ),
            min_social_links_for_presence=int(
                raw.get("min_social_links_for_presence", cls.min_social_links_for_presence)
            ),
            weights=weights,
            qualified_threshold=float(raw.get("qualified_threshold", cls.qualified_threshold)),
        )


class LeadQualityScorer(BaseScorer):
    def __init__(self, *, config: LeadQualityScorerConfig | None = None):
        self._config = config or LeadQualityScorerConfig(weights=LeadQualityScorerConfig.defaults_weights())

    def score(self, leads: list[Lead]) -> list[Lead]:
        for lead in leads:
            signals = _compute_signals(lead, self._config)
            score, evidence = _score_from_signals(signals, self._config)

            lead.flags.update(signals)
            lead.lead_score = round(score, 3)
            lead.qualified = score >= self._config.qualified_threshold
            lead.evidence.extend(evidence)
        return leads


def _compute_signals(lead: Lead, config: LeadQualityScorerConfig) -> dict[str, bool]:
    no_website_listed = not bool((lead.website or "").strip())

    no_website_verified = False
    verified_keys = [
        "website_verified",
        "website_found",
        "verified_website_found",
        "website_verification",
    ]
    for key in verified_keys:
        if key not in lead.flags:
            continue
        value = lead.flags.get(key)
        if isinstance(value, bool):
            if value is False:
                no_website_verified = True
        elif isinstance(value, str):
            if value.strip().lower() in {"not_found", "none", "no", "false", "missing"}:
                no_website_verified = True

    review_count = lead.review_count
    low_reviews = review_count is None or review_count < config.low_reviews_threshold

    incomplete_profile = any(
        [
            not bool((lead.phone or "").strip()),
            not bool((lead.address or "").strip()),
            not bool((lead.category or "").strip()),
        ]
    )

    social_count = len({k: v for k, v in (lead.social_links or {}).items() if str(v).strip()})
    has_social_presence = social_count >= config.min_social_links_for_presence

    weak_presence = (not has_social_presence) and (
        no_website_listed or low_reviews or (lead.rating is None) or (lead.rating is not None and lead.rating < 4.0)
    )

    inactive_social = False
    last_post_days = _extract_last_post_days(lead.flags)
    if last_post_days is not None:
        inactive_social = last_post_days >= config.inactive_social_days_threshold
    else:
        inactive_social = has_social_presence and (no_website_listed and low_reviews)

    return {
        "no_website_listed": no_website_listed,
        "no_website_verified": no_website_verified,
        "low_reviews": low_reviews,
        "incomplete_profile": incomplete_profile,
        "weak_presence": weak_presence,
        "inactive_social": inactive_social,
    }


def _extract_last_post_days(flags: dict[str, Any]) -> int | None:
    candidates = [
        "social_last_post_days",
        "last_social_post_days",
        "last_post_days",
    ]
    for key in candidates:
        if key not in flags:
            continue
        value = flags.get(key)
        try:
            return int(value)
        except Exception:
            pass

    ts_candidates = [
        "social_last_post_ts",
        "last_social_post_ts",
        "last_post_ts",
    ]
    for key in ts_candidates:
        if key not in flags:
            continue
        value = flags.get(key)
        dt = _coerce_datetime(value)
        if dt is None:
            continue
        now = datetime.now(timezone.utc)
        return max(0, int((now - dt).total_seconds() // 86400))

    return None


def _coerce_datetime(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, (int, float)):
        try:
            return datetime.fromtimestamp(float(value), tz=timezone.utc)
        except Exception:
            return None
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        try:
            if text.endswith("Z"):
                text = text[:-1] + "+00:00"
            return datetime.fromisoformat(text).astimezone(timezone.utc)
        except Exception:
            return None
    return None


def _score_from_signals(
    signals: dict[str, bool], config: LeadQualityScorerConfig
) -> tuple[float, list[dict[str, Any]]]:
    score = 0.0
    evidence: list[dict[str, Any]] = []
    weights = config.weights or LeadQualityScorerConfig.defaults_weights()

    for factor, active in signals.items():
        weight = float(weights.get(factor, 0.0))
        contribution = weight if active else 0.0
        score += contribution
        evidence.append(
            {
                "type": "lead_quality_factor",
                "factor": factor,
                "active": active,
                "weight": weight,
                "contribution": contribution,
            }
        )

    evidence.append(
        {
            "type": "lead_quality_summary",
            "lead_score": round(score, 3),
            "qualified_threshold": config.qualified_threshold,
            "qualified": score >= config.qualified_threshold,
        }
    )
    return score, evidence

