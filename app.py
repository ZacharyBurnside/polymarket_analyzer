import json
import os
import re
import subprocess
import threading
import requests as req
from flask import Flask, jsonify, request
from sqlalchemy import create_engine, text

BASE       = os.path.dirname(os.path.abspath(__file__))
PYTHON_BIN = '/home/zburnside/.local/bin/python3'

if not os.path.exists(PYTHON_BIN):
    PYTHON_BIN = '/usr/bin/python3'

app    = Flask(__name__)
status = {}  # keyed by tag_slug

# ── DB engine (lazy init) ─────────────────────────────────────────────────────

_engine = None

def get_engine():
    global _engine
    if _engine is None:
        db_url = (
            f"mysql+pymysql://zburnside:Bearsocks24!"
            f"@zburnside.mysql.pythonanywhere-services.com/zburnside$polymarket"
        )
        _engine = create_engine(db_url, pool_recycle=280)
    return _engine

# ── Polymarket headers (still used for resolution lookup) ────────────────────

POLYMARKET_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    'Accept': 'application/json',
    'Referer': 'https://polymarket.com/',
    'Origin': 'https://polymarket.com',
}

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

def is_sports_trade(trade: dict) -> bool:
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


# ── Intelligence pipeline ─────────────────────────────────────────────────────

def run_pipeline(tag_slug):
    status[tag_slug] = {"state": "scraping", "tag": tag_slug, "error": None}
    try:
        main_py = os.path.join(BASE, 'main.py')
        proc = subprocess.Popen(
            [PYTHON_BIN, main_py, tag_slug],
            cwd=BASE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        for line in proc.stdout:
            line = line.decode().strip()
            if 'analyzing' in line.lower() or 'analysis complete' in line.lower():
                status[tag_slug]["state"] = "analyzing"
        proc.wait()
        if proc.returncode != 0:
            err  = proc.stderr.read().decode().strip().splitlines()
            last = next((l for l in reversed(err) if l.strip()), 'Unknown error')
            status[tag_slug] = {"state": "error", "tag": tag_slug, "error": last}
            return
        status[tag_slug] = {"state": "done", "tag": tag_slug, "error": None}
    except Exception as e:
        status[tag_slug] = {"state": "error", "tag": tag_slug, "error": str(e)}


# ── Routes ────────────────────────────────────────────────────────────────────

@app.route('/')
def index():
    with open(os.path.join(BASE, 'index.html')) as f:
        return f.read()


@app.route('/api/report')
def get_report():
    tag  = request.args.get('tag', 'iran')
    path = os.path.join(BASE, f'report_{tag}.json')
    if not os.path.exists(path):
        return jsonify({"error": "No report yet"}), 404
    with open(path) as f:
        return jsonify(json.load(f))


@app.route('/api/run', methods=['POST'])
def run():
    tag = request.json.get('tag', '').strip().lower()
    if not tag:
        return jsonify({"error": "No tag provided"}), 400
    if status.get(tag, {}).get('state') in ('scraping', 'analyzing'):
        return jsonify({"error": f"Pipeline already running for '{tag}'"}), 429
    threading.Thread(target=run_pipeline, args=(tag,), daemon=True).start()
    return jsonify({"ok": True, "tag": tag})


@app.route('/api/status')
def get_status():
    tag = request.args.get('tag', '')
    if tag:
        return jsonify(status.get(tag, {"state": "idle", "tag": tag, "error": None}))
    return jsonify(status)


@app.route('/api/trades')
def get_trades():
    """
    Serves whale tracker data from the MySQL DB instead of hitting
    the Polymarket API live. The collector.py script keeps the DB fresh
    on a scheduled basis.

    Filters supported:
      filterAmount  — minimum usd_cost (default 10000)
      side          — BUY / SELL / ALL (default ALL)
      startTs       — unix timestamp floor (default: no filter)
      limit         — max rows to return (default 1000, max 5000)
    """
    filter_amount = float(request.args.get('filterAmount', 10000))
    side          = request.args.get('side', 'ALL').upper()
    start_ts      = request.args.get('startTs')
    limit         = min(int(request.args.get('limit', 1000)), 5000)

    # Build query dynamically
    conditions = ['usd_cost >= :filter_amount']
    params     = {'filter_amount': filter_amount, 'limit': limit}

    if side in ('BUY', 'SELL'):
        conditions.append('side = :side')
        params['side'] = side

    if start_ts:
        try:
            conditions.append('timestamp >= :start_ts')
            params['start_ts'] = int(start_ts)
        except ValueError:
            pass

    where = ' AND '.join(conditions)
    sql = text(f"""
        SELECT
            transactionHash, proxyWallet, side,
            size, price, usd_cost,
            conditionId, title, slug, outcome, outcomeIndex,
            icon, eventSlug, name, pseudonym, bio, profileImage,
            is_sports, timestamp
        FROM trades
        WHERE {where}
        ORDER BY timestamp DESC
        LIMIT :limit
    """)

    try:
        with get_engine().connect() as conn:
            rows = conn.execute(sql, params).mappings().all()

        # Convert to list of dicts matching the shape the frontend expects
        trades = []
        for r in rows:
            t = {
                'transactionHash':  r['transactionHash'],
                'proxyWallet':      r['proxyWallet'],
                'side':             r['side'],
                'size':             float(r['size']),
                'price':            float(r['price']),
                'conditionId':      r['conditionId'],
                'title':            r['title'],
                'slug':             r['slug'],
                'outcome':          r['outcome'],
                'outcomeIndex':     r['outcomeIndex'],
                'icon':             r['icon'],
                'eventSlug':        r['eventSlug'],
                'name':             r['name'],
                'pseudonym':        r['pseudonym'],
                'bio':              r['bio'],
                'profileImage':     r['profileImage'],
                'timestamp':        r['timestamp'],
                '_isSports':        bool(r['is_sports']),
            }
            trades.append(t)

        # ── Resolution lookup from Gamma ──────────────────────────────────
        condition_ids = list({
            t['conditionId'] for t in trades
            if t.get('conditionId') and not t['_isSports']
        })

        resolution_map = {}
        for i in range(0, len(condition_ids), 20):
            chunk = condition_ids[i:i + 20]
            try:
                gr = req.get(
                    'https://gamma-api.polymarket.com/markets',
                    params={'condition_ids': ','.join(chunk), 'limit': len(chunk)},
                    headers=POLYMARKET_HEADERS,
                    timeout=10
                )
                if not gr.ok:
                    continue
                for m in gr.json():
                    cid = m.get('conditionId')
                    if not cid:
                        continue
                    closed = m.get('closed', False)
                    try:
                        raw_prices   = m.get('outcomePrices', '[]')
                        raw_outcomes = m.get('outcomes', '[]')
                        price_list   = json.loads(raw_prices)   if isinstance(raw_prices,   str) else raw_prices
                        outcome_list = json.loads(raw_outcomes) if isinstance(raw_outcomes, str) else raw_outcomes
                        winner = None
                        if closed and price_list:
                            for idx, p in enumerate(price_list):
                                if float(p) >= 0.99:
                                    winner = outcome_list[idx] if idx < len(outcome_list) else None
                                    break
                        resolution_map[cid] = {'resolved': closed, 'winner': winner}
                    except Exception:
                        resolution_map[cid] = {'resolved': False, 'winner': None}
            except Exception:
                pass

        # ── Attach resolution ─────────────────────────────────────────────
        for t in trades:
            if t['_isSports']:
                t['_resolved']  = False
                t['_winner']    = None
                t['_betResult'] = 'sports'
                continue
            res = resolution_map.get(t.get('conditionId'), {})
            t['_resolved'] = res.get('resolved', False)
            t['_winner']   = res.get('winner')
            if res.get('resolved') and res.get('winner'):
                t['_betResult'] = 'won' if t.get('outcome') == res['winner'] else 'lost'
            else:
                t['_betResult'] = 'open'

        return jsonify({
            'trades':      trades,
            'count':       len(trades),
            'exhausted':   True,   # DB query always returns complete result set
            'limit_used':  limit,
            'pages_fetched': 1,
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/profile')
def get_profile():
    """
    Scrape public profile stats from polymarket.com/@{username}
    and proxy positions + activity from data-api.

    Params:
      user     — proxyWallet address (required)
      username — display name for @ URL (optional, falls back to address-based URL)
    """
    wallet   = request.args.get('user', '').strip()
    username = request.args.get('username', '').strip()

    if not wallet:
        return jsonify({'error': 'user param required'}), 400

    result = {'wallet': wallet, 'username': username}

    # ── 1. Scrape HTML profile page ───────────────────────────────────────
    # Try @username first, fall back to /profile/{address}
    profile_urls = []
    if username:
        profile_urls.append(f'https://polymarket.com/@{username}')
    profile_urls.append(f'https://polymarket.com/profile/{wallet}')

    html = None
    for url in profile_urls:
        try:
            r = req.get(url, headers={
                **POLYMARKET_HEADERS,
                'Accept': 'text/html,application/xhtml+xml',
            }, timeout=10)
            if r.ok and len(r.text) > 1000:
                html = r.text
                result['profile_url'] = url
                break
        except Exception:
            continue

    if html:
        def extract(pattern, default='—'):
            m = re.search(pattern, html)
            return m.group(1).strip() if m else default

        # Username
        result['display_name'] = extract(
            r'class="text-2xl font-semibold text-primary truncate[^"]*">([^<]+)<', '—'
        )

        # Joined date — "Joined<!-- --> <!-- -->Mar 2026"
        result['joined'] = extract(
            r'Joined(?:<!--\s*-->\s*){1,3}([A-Za-z]+ \d{4})', '—'
        )

        # Views — "506<!-- --> <!-- -->views"
        result['views'] = extract(
            r'([\d,]+)(?:<!--\s*-->\s*){1,3}views', '—'
        )

        # Stats — each stat is:
        # <p class="text-lg font-medium text-text-primary">$14.7M</p>
        # <p class="text-xs font-medium text-text-secondary whitespace-nowrap">Positions Value</p>
        stat_pairs = re.findall(
            r'<p class="text-lg font-medium text-text-primary">([^<]+)</p>\s*'
            r'<p class="text-xs font-medium text-text-secondary whitespace-nowrap">([^<]+)</p>',
            html
        )
        for val, label in stat_pairs:
            val   = val.strip()
            label = label.strip().lower()
            if 'position' in label:
                result['positions_value'] = val
            elif 'biggest' in label or 'win' in label:
                result['biggest_win'] = val
            elif 'prediction' in label:
                result['predictions'] = val
            elif 'profit' in label or 'pnl' in label:
                result['profit'] = val
            elif 'volume' in label:
                result['volume'] = val

    # ── 2. Positions from data-api ────────────────────────────────────────
    try:
        r = req.get(
            'https://data-api.polymarket.com/positions',
            params={
                'user':          wallet,
                'sortBy':        'CURRENT',
                'sortDirection': 'DESC',
                'sizeThreshold': 0.1,
                'limit':         30,
                'offset':        0,
            },
            headers=POLYMARKET_HEADERS,
            timeout=10
        )
        result['positions'] = r.json() if r.ok else []
    except Exception:
        result['positions'] = []

    # ── 3. Activity from data-api ─────────────────────────────────────────
    try:
        r = req.get(
            'https://data-api.polymarket.com/activity',
            params={
                'user':   wallet,
                'limit':  30,
                'offset': 0,
            },
            headers=POLYMARKET_HEADERS,
            timeout=10
        )
        activity = r.json() if r.ok else []
        result['activity'] = activity

        # Derive first_seen from oldest trade in activity
        # For true first_seen hit activity with ASC sort
        trades_only = [a for a in activity if a.get('type') == 'TRADE']
        if trades_only:
            result['latest_trade_ts'] = max(a['timestamp'] for a in trades_only)
    except Exception:
        result['activity'] = []

    # ── 4. First seen — oldest trade timestamp ────────────────────────────
    try:
        r = req.get(
            'https://data-api.polymarket.com/activity',
            params={
                'user':          wallet,
                'type':          'TRADE',
                'sortBy':        'TIMESTAMP',
                'sortDirection': 'ASC',
                'limit':         1,
            },
            headers=POLYMARKET_HEADERS,
            timeout=10
        )
        if r.ok and r.json():
            result['first_seen_ts'] = r.json()[0].get('timestamp')
    except Exception:
        pass

    return jsonify(result)


def debug():
    main_py = os.path.join(BASE, 'main.py')
    proc = subprocess.Popen(
        [PYTHON_BIN, main_py, 'iran'],
        cwd=BASE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE
    )
    stdout, stderr = proc.communicate()
    return jsonify({
        "returncode": proc.returncode,
        "stdout":     stdout.decode(),
        "stderr":     stderr.decode(),
        "python_bin": PYTHON_BIN,
        "main_py":    main_py,
        "exists":     os.path.exists(main_py)
    })


if __name__ == '__main__':
    app.run(debug=True)