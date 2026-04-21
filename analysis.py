import anthropic
import pandas as pd
import ast
import json
import os
from datetime import datetime


SYSTEM_PROMPT = """You are a sharp, quantitative prediction market analyst. Your job is to read live Polymarket data and produce a structured intelligence briefing.

Rules you must follow:
- Every claim must be grounded in a specific market price or price change from the data. Never speculate beyond what the numbers show.
- Prices are probabilities. 0.36 = 36%. Always convert and express as percentages.
- day_change and week_change are percentage point shifts (0.05 = +5pp). These are your most important signals — they show where the market is moving, not just where it sits.
- Lead with what is CHANGING, not what is static. A market at 80% that hasn't moved is less interesting than one at 30% that jumped 12pp this week.
- Be direct and specific. Name the exact market, cite the exact number. No vague language.
- Write like a briefing for a senior analyst — no filler, no hedging, no meta-commentary about the data.
- Never mention data quality, limitations, or missing fields. Work with what you have.

Output format — you must use EXACTLY these 5 section headers on their own line:

1. [THEME]
2. [THEME]
3. [THEME]
4. [THEME]
5. Key Shifts This Week

Where [THEME] is the most important theme you identify from the data. Section 5 is always the biggest weekly movers. Each section: 3-5 sentences. Dense, specific, no padding."""


def extract_markets(df: pd.DataFrame) -> list:
    rows = []
    for _, row in df.iterrows():
        try:
            m_raw = row['markets']
            markets = m_raw if isinstance(m_raw, list) else ast.literal_eval(m_raw)
            for m in markets:
                price = m.get('lastTradePrice')
                if not price or float(price) <= 0:
                    continue
                rows.append({
                    'question':     m.get('question', '').strip(),
                    'price':        round(float(price), 4),
                    'volume':       round(float(m.get('volumeNum', 0)), 2),
                    'day_change':   m.get('oneDayPriceChange'),
                    'week_change':  m.get('oneWeekPriceChange'),
                    'month_change': m.get('oneMonthPriceChange'),
                    'end_date':     m.get('endDateIso', ''),
                })
        except Exception:
            continue

    rows.sort(key=lambda x: x['volume'], reverse=True)
    return rows[:50]


def build_prompt(df: pd.DataFrame, tag_slug: str) -> str:
    markets = extract_markets(df)
    now = datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')

    movers = sorted(
        [r for r in markets if r['week_change'] is not None],
        key=lambda x: abs(x['week_change']),
        reverse=True
    )[:10]

    return f"""Polymarket data — category: '{tag_slug}' — scraped at {now}

Analyzing {len(markets)} markets (top 50 by volume).

Identify the dominant themes from the data. Name sections after those themes. Section 5 must always be "Key Shifts This Week."

BIGGEST WEEKLY MOVERS:
{json.dumps(movers, indent=2)}

ALL MARKETS:
{json.dumps(markets, indent=2)}

Start directly with "1." — no preamble."""


def analyze(df: pd.DataFrame, tag_slug: str = 'unknown') -> dict:
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise ValueError("ANTHROPIC_API_KEY environment variable not set")

    client = anthropic.Anthropic(api_key=api_key)

    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=2000,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": build_prompt(df, tag_slug)}]
    )

    return {
        "timestamp":     datetime.utcnow().isoformat(),
        "tag_slug":      tag_slug,
        "analysis":      response.content[0].text,
        "input_tokens":  response.usage.input_tokens,
        "output_tokens": response.usage.output_tokens,
    }