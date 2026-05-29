"""LLM layer: natural language query parsing + deal quality scoring."""
from __future__ import annotations
import json
import os
from typing import Optional

from .models import Product, SearchQuery


def _client():
    try:
        import openai
        return openai.OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    except Exception:
        return None


def parse_query(user_text: str) -> SearchQuery:
    """Turn a free-text query into structured SearchQuery.
    Falls back to simple keyword search if no LLM key."""
    api = _client()
    if not api:
        return SearchQuery(keywords=user_text)

    system = (
        "You extract e-commerce search parameters from natural language. "
        "Return ONLY valid JSON matching this schema:\n"
        "{\"keywords\":\"...\", \"min_discount\": number (default 50), "
        "\"max_price\": number or null, \"min_price\": number or null, "
        "\"category\": string or null, \"sources\": [\"amazon\",\"flipkart\",\"myntra\"] or subset, "
        "\"min_rating\": number or null}"
    )
    model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    try:
        resp = api.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user_text},
            ],
            temperature=0,
            max_tokens=256,
        )
        raw = resp.choices[0].message.content or ""
        raw = raw.strip()
        if raw.startswith("```"):
            raw = raw.strip("`").strip("json").strip()
        data = json.loads(raw)
        return SearchQuery(**data)
    except Exception:
        # Graceful fallback
        return SearchQuery(keywords=user_text)


def rank_deals(products: list[Product]) -> list[Product]:
    """Re-rank products by a composite deal score.
    Uses LLM if available, else uses a heuristic score."""
    api = _client()
    if not api or len(products) == 0:
        return _heuristic_rank(products)

    model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    batch = products[:30]  # limit API cost
    summaries = [
        f"- {p.title} (₹{p.price} vs ₹{p.mrp}, {p.discount_pct}% off, {p.rating}* from {p.source})"
        for p in batch
    ]
    prompt = (
        "Rate the following Indian e-commerce deals from 0 (bad) to 100 (amazing). "
        "Consider discount depth, rating, and source reputation.\n\n"
        + "\n".join(summaries)
        + "\n\nReturn ONLY a JSON object mapping the product index (0-based integer string) to its score:\n"
        "{\"0\": 78, \"1\": 45, ...}"
    )
    try:
        resp = api.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
            max_tokens=512,
        )
        raw = resp.choices[0].message.content or ""
        raw = raw.strip()
        if raw.startswith("```"):
            raw = raw.strip("`").strip("json").strip()
        scores = json.loads(raw)
        scored = []
        for i, p in enumerate(batch):
            p_score = float(scores.get(str(i), 0))
            scored.append((p, p_score))
        scored.sort(key=lambda x: x[1], reverse=True)
        return [x[0] for x in scored] + products[30:]
    except Exception:
        return _heuristic_rank(products)


def _heuristic_rank(products: list[Product]) -> list[Product]:
    def score(p: Product) -> float:
        disc = p.discount_pct
        rat = (p.rating or 4.0) / 5.0 * 20  # max 20
        rev = min((p.reviews or 0) / 1000, 10)  # max 10
        return disc + rat + rev
    return sorted(products, key=score, reverse=True)
