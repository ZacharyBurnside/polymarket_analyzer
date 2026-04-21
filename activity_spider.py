import os
import re
import time
import requests
from datetime import datetime
from sqlalchemy import create_engine, text

# ── Config ────────────────────────────────────────────────────────────────────

DB_URL = (
    f"mysql+pymysql://zburnside:Bearsocks24!"
    f"@zburnside.mysql.pythonanywhere-services.com/zburnside$polymarket"
)

POLYMARKET_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    'Accept':     'application/json',
    'Referer':    'https://polymarket.com/',
    'Origin':     'https://polymarket.com',
}

FILTER_AMOUNT = 10000
PAGE_SIZE     = 500
MAX_PAGES     = 20

# ── Sports detection ──────────────────────────────────────────────────────────

SPORTS_ICON_PATTERN = re.compile(
    r'(?i)(nhl|nba|nfl|mlb|wnba|nascar|ncaa|ufc|mma|fifa|epl|mls|pga|atp|wta|'
    r'f1|formula.?1|rugby|cricket|tennis|golf|boxing|wrestling|'
    r'lakers|celtics|warriors|knicks|bulls|heat|nets|bucks|suns|'
    r'chiefs|patriots|cowboys|eagles|packers|49ers|ravens|bills|'
    r'yankees|dodgers|astros|braves|cubs|red.?sox|'
    r'sport|league|champion|trophy|cup|bowl|series|finals|playoffs?)'
)
SPORTS_SLUG_PATTERN = re.compile(
    r'(?i)(^nhl-|^nba-|^nfl-|^mlb-|^wnba-|^mls-|^ufc-|^ncaa-|'
    r'-vs-|-at-[a-z]{2,4}-\d{4}-|'
    r'-\d{4}-\d{2}-\d{2}$|'
    r'super.?bowl|stanley.?cup|world.?series|nba.?finals|'
    r'champion|playoff|bracket|draft)'
)
SPORTS_TITLE_PATTERN = re.compile(
    r'(?i)('
    r'\bnfl\b|\bnba\b|\bnhl\b|\bmlb\b|\bwnba\b|\bmls\b|\bufc\b|\bncaa\b|'
    r'\bufl\b|\bcfl\b|\bxfl\b|\bafl\b|\bnll\b|'
    r'premier league|champions league|europa league|la liga|serie a|bundesliga|ligue 1|'
    r'world cup|super bowl|stanley cup|world series|nba finals|'
    r'grand prix|formula 1|\bf1\b|indycar|nascar|'
    r'wimbledon|us open|french open|australian open|'
    r'\bplayoffs?\b|\bpostseason\b|\bbracket\b|\bdraft\b|\btrade deadline\b|'
    r'championship game|title game|bowl game|'
    r'mvp|cy young|heisman|norris trophy|hart trophy|vezina|'
    r'golden glove|silver slugger|rookie of the year|'
    r'\bvs\.?\s+[A-Z]|[A-Z][a-z]+\s+vs\.?\s+[A-Z]|'
    r'win the \d{4}|advance to|make the playoffs|clinch|'
    r'total (goals?|points?|runs?|touchdowns?|rebounds?|assists?)|'
    r'\bo\/u\b|\bover\/under\b|point spread|'
    r'passing yards|rushing yards|receiving yards|'
    r'home run|strikeout|rebound|assist|three.pointer'
    r')'
)

def is_sports(trade: dict) -> bool:
    icon  = trade.get('icon',      '') or ''
    slug  = trade.get('slug',      '') or ''
    title = trade.get('title',     '') or ''
    event = trade.get('eventSlug', '') or ''
    return bool(
        SPORTS_ICON_PATTERN.search(icon)  or
        SPORTS_SLUG_PATTERN.search(slug)  or
        SPORTS_SLUG_PATTERN.search(event) or
        SPORTS_TITLE_PATTERN.search(title)
    )

# ── Fetch ─────────────────────────────────────────────────────────────────────

def fetch_trades(stop_at_hash: str = None) -> list:
    all_trades = []
    seen       = set()

    for page in range(MAX_PAGES):
        params = {
            'takerOnly':    'true',
            'limit':        PAGE_SIZE,
            'offset':       page * PAGE_SIZE,
            'filterType':   'CASH',
            'filterAmount': FILTER_AMOUNT,
        }
        try:
            r = requests.get(
                'https://data-api.polymarket.com/trades',
                params=params,
                headers=POLYMARKET_HEADERS,
                timeout=15
            )
            r.raise_for_status()
            page_data = r.json()
        except Exception as e:
            print(f"  [fetch] page {page} error: {e}")
            break

        if not page_data:
            break

        stop = False
        for t in page_data:
            tx = t.get('transactionHash', '')
            if not tx or tx in seen:
                continue
            seen.add(tx)

            if stop_at_hash and tx == stop_at_hash:
                stop = True
                break

            all_trades.append(t)

        if stop or len(page_data) < PAGE_SIZE:
            break

        time.sleep(0.3)

    return all_trades

# ── DB helpers ────────────────────────────────────────────────────────────────

def get_newest_hash(engine) -> str | None:
    with engine.connect() as conn:
        result = conn.execute(
            text("SELECT transactionHash FROM trades ORDER BY timestamp DESC LIMIT 1")
        )
        row = result.fetchone()
        return row[0] if row else None

def insert_trades(engine, trades: list) -> int:
    if not trades:
        return 0

    rows = []
    for t in trades:
        size     = float(t.get('size',  0) or 0)
        price    = float(t.get('price', 0) or 0)
        usd_cost = size * price
        if usd_cost > 1_000_000:
            usd_cost = usd_cost / 1_000_000

        rows.append({
            'transactionHash': t.get('transactionHash'),
            'proxyWallet':     t.get('proxyWallet'),
            'side':            t.get('side'),
            'size':            size,
            'price':           price,
            'usd_cost':        round(usd_cost, 6),
            'conditionId':     t.get('conditionId'),
            'title':           t.get('title'),
            'slug':            t.get('slug'),
            'outcome':         t.get('outcome'),
            'outcomeIndex':    t.get('outcomeIndex'),
            'icon':            t.get('icon'),
            'eventSlug':       t.get('eventSlug'),
            'name':            t.get('name'),
            'pseudonym':       t.get('pseudonym'),
            'bio':             t.get('bio'),
            'profileImage':    t.get('profileImage'),
            'is_sports':       1 if is_sports(t) else 0,
            'timestamp':       t.get('timestamp'),
        })

    sql = text("""
        INSERT IGNORE INTO trades (
            transactionHash, proxyWallet, side, size, price, usd_cost,
            conditionId, title, slug, outcome, outcomeIndex,
            icon, eventSlug, name, pseudonym, bio, profileImage,
            is_sports, timestamp
        ) VALUES (
            :transactionHash, :proxyWallet, :side, :size, :price, :usd_cost,
            :conditionId, :title, :slug, :outcome, :outcomeIndex,
            :icon, :eventSlug, :name, :pseudonym, :bio, :profileImage,
            :is_sports, :timestamp
        )
    """)

    with engine.begin() as conn:
        result = conn.execute(sql, rows)

    return result.rowcount

# ── Main ──────────────────────────────────────────────────────────────────────

def run():
    started = datetime.utcnow()
    print(f"[{started}] collector starting")

    engine = create_engine(DB_URL)

    try:
        newest_hash = get_newest_hash(engine)
        print(f"  newest stored hash: {newest_hash or '(none — first run)'}")

        trades = fetch_trades(stop_at_hash=newest_hash)
        print(f"  fetched {len(trades)} new trades from API")

        inserted = insert_trades(engine, trades)
        print(f"  inserted {inserted} new rows into DB")

        with engine.connect() as conn:
            total      = conn.execute(text("SELECT COUNT(*) FROM trades")).scalar()
            non_sports = conn.execute(text("SELECT COUNT(*) FROM trades WHERE is_sports = 0")).scalar()

        print(f"  DB totals: {total} trades ({non_sports} non-sports)")

    finally:
        engine.dispose()

    elapsed = (datetime.utcnow() - started).total_seconds()
    print(f"[{datetime.utcnow()}] done in {elapsed:.1f}s")


if __name__ == '__main__':
    run()