from __future__ import annotations

import json
from typing import Any

from .db import json_dumps
from .utils import number_or_none, pick, text_or_none, utc_now_iso


def normalize_signal(raw: dict[str, Any]) -> dict[str, Any]:
    token = pick(raw, "token", "pair", default={}) or {}
    notification_id = text_or_none(
        pick(raw, "notificationId", "notification_id", "id", "uuid")
    )
    mint = text_or_none(
        pick(raw, "mint", "tokenAddress", "ca", "address")
        or pick(token, "mint", "address", "tokenAddress")
    )
    created = text_or_none(
        pick(raw, "createdOn", "created_on", "createdAt", "created_at", "timestamp", "sentAt")
    )
    market_cap = number_or_none(
        pick(raw, "marketCap", "market_cap", "mc")
        or pick(token, "marketCap", "market_cap", "mc")
    )
    return {
        "notification_id": notification_id or f"{mint or 'unknown'}:{created or utc_now_iso()}",
        "mint": mint,
        "symbol": text_or_none(pick(raw, "symbol") or pick(token, "symbol")),
        "name": text_or_none(pick(raw, "name") or pick(token, "name")),
        "chain": text_or_none(pick(raw, "chain") or pick(token, "chain")),
        "notification_type": text_or_none(
            pick(raw, "notificationType", "notification_type", "type")
        ),
        "sent_at": text_or_none(pick(raw, "sentAt", "sent_at", "timestamp")),
        "market_cap": market_cap,
        "first_call_market_cap": number_or_none(
            pick(raw, "firstCallMarketCap", "first_call_market_cap", "callMc", "call_mc")
            or market_cap
        ),
        "liquidity": number_or_none(pick(raw, "liquidity", "liq") or pick(token, "liquidity")),
        "price_usd": number_or_none(
            pick(raw, "priceUsd", "price_usd", "price") or pick(token, "priceUsd", "price")
        ),
        "vol_1h": number_or_none(pick(raw, "vol1h", "volume1h", "vol_1h")),
        "vol_24h": number_or_none(pick(raw, "vol24h", "volume24h", "vol_24h")),
        "chg_1h": number_or_none(pick(raw, "chg1h", "change1h", "chg_1h")),
        "chg_24h": number_or_none(pick(raw, "chg24h", "change24h", "chg_24h")),
        "total_buy": number_or_none(
            pick(raw, "totalBuy", "total_buy", "buyVolume")
            or pick(pick(raw, "trackers", default={}) or {}, "totalBuy", "total_buy", "buyVolume")
        ),
        "count_buy": int(
            number_or_none(
                pick(raw, "countBuy", "count_buy", "buys")
                or pick(pick(raw, "trackers", default={}) or {}, "countBuy", "count_buy", "buys")
            )
            or 0
        ),
        "label": text_or_none(pick(raw, "label")),
        "sentence": text_or_none(pick(raw, "sentence")),
        "paragraph": text_or_none(pick(raw, "paragraph", "description")),
        "factory": text_or_none(pick(raw, "factory")),
        "pre_factory": text_or_none(pick(raw, "preFactory", "pre_factory")),
        "total_fee": number_or_none(pick(raw, "totalFee", "total_fee")),
        "created_at": text_or_none(pick(raw, "createdAt", "created_at")),
        "first_call_time": text_or_none(pick(raw, "firstCallTime", "first_call_time", "callAt")),
        "created_on": created or utc_now_iso(),
        "raw_json": json_dumps(raw),
    }


def extract_signal_list(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if not isinstance(payload, dict):
        return []
    for key in ("signals", "data", "results", "notifications", "alerts"):
        value = payload.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
    return [payload] if payload else []


def normalize_token_quality(mint: str | None, *sources: dict[str, Any] | None) -> dict[str, Any] | None:
    if not mint:
        return None
    merged: dict[str, Any] = {}
    seen_quality_field = False
    for source in sources:
        if not isinstance(source, dict):
            continue
        raw_json = source.get("raw_json")
        if isinstance(raw_json, str):
            try:
                source = {**source, **json.loads(raw_json)}
            except json.JSONDecodeError:
                pass
        token = pick(source, "token", "data", default={}) or {}
        risk = pick(source, "risk", "security", "audit", default={}) or {}
        holders = pick(source, "holders", "holderStats", default={}) or {}
        quality_keys = {
            "holderCount",
            "holders",
            "holder_count",
            "top10Percent",
            "top10",
            "top10_percent",
            "devHoldPercent",
            "sniperHoldPercent",
            "bundleHoldPercent",
            "dexPaid",
            "dex_paid",
            "freezable",
            "mintable",
        }
        seen_quality_field = seen_quality_field or any(
            key in source or key in token or key in risk or key in holders for key in quality_keys
        )
        merged.update(source)
        merged.update(token if isinstance(token, dict) else {})
        merged.update(risk if isinstance(risk, dict) else {})
        merged.update(holders if isinstance(holders, dict) else {})
    if not merged or not seen_quality_field:
        return None
    return {
        "mint": mint,
        "holder_count": int(number_or_none(pick(merged, "holderCount", "holders", "holder_count")) or 0),
        "top10_percent": number_or_none(pick(merged, "top10Percent", "top10", "top10_percent")),
        "dev_hold_percent": number_or_none(
            pick(merged, "devHoldPercent", "dev_hold_percent", "devHoldingPercent")
        ),
        "sniper_hold_percent": number_or_none(
            pick(merged, "sniperHoldPercent", "sniper_hold_percent", "snipersHoldPercent")
        ),
        "bundle_hold_percent": number_or_none(
            pick(merged, "bundleHoldPercent", "bundle_hold_percent", "bundledPercent")
        ),
        "phishing_hold_percent": number_or_none(
            pick(merged, "phishingHoldPercent", "phishing_hold_percent")
        ),
        "dex_paid": int(bool(pick(merged, "dexPaid", "dex_paid", default=False))),
        "dex_boost_score": number_or_none(pick(merged, "dexBoostScore", "dex_boost_score")),
        "freezable": int(bool(pick(merged, "freezable", "freezeAuthority", default=False))),
        "mintable": int(bool(pick(merged, "mintable", "mintAuthority", default=False))),
        "lp_burned_percent": number_or_none(
            pick(merged, "lpBurnedPercent", "lp_burned_percent", "lpBurn")
        ),
        "updated_at": utc_now_iso(),
    }


def extract_top_holders(source: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not isinstance(source, dict):
        return []
    candidates = [
        pick(source, "topHolders", "top_holders", default=None),
        pick(source, "holders", default=None),
        pick(pick(source, "token", default={}) or {}, "topHolders", "holders", default=None),
    ]
    holder_list = next((item for item in candidates if isinstance(item, list)), [])
    normalized = []
    for holder in holder_list:
        if not isinstance(holder, dict):
            continue
        normalized.append(
            {
                "wallet": text_or_none(pick(holder, "wallet", "address", "owner")),
                "amount": number_or_none(pick(holder, "amount", "balance", "uiAmount")),
                "percent": number_or_none(pick(holder, "percent", "percentage", "share")),
                "name": text_or_none(pick(holder, "name", "label")),
                "kol_name": text_or_none(pick(holder, "kolName", "kol_name")),
                "kol_twitter": text_or_none(pick(holder, "kolTwitter", "kol_twitter", "twitter")),
            }
        )
    return normalized


def _derived_fdv(raw: dict[str, Any], price_key: str) -> float | None:
    pool = pick(raw, "pool", default={}) or {}
    base_token = pick(raw, "baseTokenInfo", default={}) or {}
    if not isinstance(pool, dict) or not isinstance(base_token, dict):
        return None
    price = number_or_none(pick(pool, price_key))
    supply = number_or_none(pick(base_token, "totalSupply", "supply"))
    if price is None or supply is None:
        return None
    return price * supply


def normalize_outcome(mint: str, raw: dict[str, Any]) -> dict[str, Any]:
    pool = pick(raw, "pool", default={}) or {}
    pool = pool if isinstance(pool, dict) else {}
    outcome_data = pick(raw, "outcome", default={}) or {}
    outcome_data = outcome_data if isinstance(outcome_data, dict) else {}
    call_mc = number_or_none(
        pick(
            raw,
            "callMc",
            "call_mc",
            "callFdv",
            "callFDV",
            "call_fdv",
            "firstCallMarketCap",
            "firstCallFdv",
            "firstCallFDV",
        )
    )
    current_mc = number_or_none(
        pick(raw, "currentMc", "current_mc", "currentFdv", "currentFDV", "marketCap", "fdv")
        or pick(pool, "marketCap", "fdv", "fullyDilutedValuation")
        or _derived_fdv(raw, "priceUsd")
    )
    ath_mc = number_or_none(
        pick(
            raw,
            "athMc",
            "ath_mc",
            "ath",
            "athMarketCap",
            "athFdv",
            "athFDV",
            "maxFdv",
            "maxFDV",
            "maxMarketCap",
        )
        or pick(pool, "marketCapAth", "fdvAth", "maxFdv", "maxFDV")
        or _derived_fdv(raw, "priceUsdAth")
    )
    max_multiple = number_or_none(pick(raw, "maxMultiple", "max_multiple", "multiple"))
    milestone_best_mc = None
    for key in (
        "max_mc_10m",
        "max_mc_30m",
        "max_mc_1h",
        "max_mc_24h",
        "max_fdv_10m",
        "max_fdv_30m",
        "max_fdv_1h",
        "max_fdv_24h",
    ):
        mc = number_or_none(pick(outcome_data, key))
        if mc is not None:
            milestone_best_mc = max(milestone_best_mc or mc, mc)
    milestones = pick(raw, "milestones", default={}) or {}
    if isinstance(milestones, dict):
        milestone_map = pick(milestones, "milestones", default={}) or {}
        if isinstance(milestone_map, dict):
            for milestone in milestone_map.values():
                if isinstance(milestone, dict):
                    mc = number_or_none(pick(milestone, "mc"))
                    if mc is not None:
                        milestone_best_mc = max(milestone_best_mc or mc, mc)
        timeline = pick(milestones, "timeline", default=[]) or []
        if isinstance(timeline, list):
            for event in timeline:
                if isinstance(event, dict):
                    mc = number_or_none(pick(event, "mc"))
                    if mc is not None:
                        milestone_best_mc = max(milestone_best_mc or mc, mc)
    best_mc_values = [value for value in (ath_mc, current_mc, milestone_best_mc) if value is not None]
    best_mc = max(best_mc_values) if best_mc_values else None
    if ath_mc is None and best_mc is not None:
        ath_mc = best_mc
    if max_multiple is None and call_mc and best_mc:
        max_multiple = best_mc / call_mc
    return {
        "mint": mint,
        "call_mc": call_mc,
        "call_at": text_or_none(pick(raw, "callAt", "call_at", "firstCallTime")),
        "current_mc": current_mc,
        "ath_mc": ath_mc,
        "ath_at": text_or_none(pick(raw, "athAt", "ath_at")),
        "max_multiple": max_multiple,
        "outcome_bucket": outcome_bucket(max_multiple),
        "rugged": int(bool(pick(raw, "rugged", "isRugged", default=False))),
        "next_milestone": next_milestone(max_multiple),
        "updated_at": utc_now_iso(),
        "raw_json": json_dumps(raw),
    }


def outcome_bucket(max_multiple: float | None) -> str | None:
    if max_multiple is None:
        return None
    if max_multiple < 2:
        return "<2x"
    if max_multiple < 5:
        return "2x-5x"
    if max_multiple < 10:
        return "5x-10x"
    if max_multiple < 20:
        return "10x-20x"
    return "20x+"


MILESTONES = [
    1.5,
    2.0,
    3.0,
    4.0,
    5.0,
    10.0,
    20.0,
    30.0,
    40.0,
    50.0,
    75.0,
    100.0,
    150.0,
    200.0,
]


def hit_milestones(max_multiple: float | None) -> list[float]:
    if max_multiple is None:
        return []
    return [milestone for milestone in MILESTONES if max_multiple >= milestone]


def next_milestone(max_multiple: float | None) -> float | None:
    if max_multiple is None:
        return MILESTONES[0]
    for milestone in MILESTONES:
        if max_multiple < milestone:
            return milestone
    return None
