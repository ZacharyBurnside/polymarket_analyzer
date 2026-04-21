# Polymarket Analyzer

An automated intelligence briefing system that scrapes live prediction market data from Polymarket and generates structured analyst reports using Claude AI. Covers markets across geopolitics, crypto, elections, equities, and sports.

---

## What It Does

1. **Scrapes** live event and market data from Polymarket's API by topic/tag
2. **Analyzes** the top 50 markets by volume using Claude (claude-sonnet-4-6)
3. **Generates** a structured 5-section briefing focused on price movements and key shifts
4. **Saves** the report as a JSON file with market data and AI analysis

The system is designed to surface *what is moving*, not just where prices sit — week-over-week and month-over-month changes are the primary signal.

---

## Sample Output Topics

| Tag | Description |
|---|---|
| `iran` | US military action, regime stability, Strait of Hormuz, nuclear deal |
| `israel` | Gaza ceasefire, Hamas, Lebanon offensive, Iran-Israel conflict |
| `trump` | Greenland, Venezuela, Iran escalation, China diplomacy |
| `bitcoin` | BTC price targets, MicroStrategy, institutional moves |
| `crypto` | Token launches, ETH, FDV valuations |
| `economy` | Fed rate path, NVIDIA market cap, recession risk |
| `elections` | 2028 presidential nomination markets |
| `equities` | NVIDIA, Tesla, Google, S&P 500 price targets, earnings |
| `sports` | NHL, NBA, Champions League, Premier League, FIFA |

---

## Tech Stack

- **Python** — scraping, data pipeline, CLI
- **Anthropic API** — Claude claude-sonnet-4-6 for analysis
- **Pandas** — data processing
- **SQLAlchemy + MySQL** — trade data storage (activity spider)
- **Requests** — HTTP scraping

---

## File Structure

```
polymarket_analyzer/
├── main.py              # Entry point — runs full pipeline for a given tag
├── scraper.py           # Hits Polymarket Gamma API, returns DataFrame
├── analysis.py          # Sends market data to Claude, returns structured report
├── activity_spider.py   # Separate collector — scrapes large trades (>$10K) into MySQL
├── app.py               # Web interface
├── report_*.json        # Generated reports by topic
└── latest_report.json   # Most recent report
```

---

## Usage

```bash
# Run analysis for a specific tag
python main.py iran
python main.py bitcoin
python main.py economy

# Collect large trades into database
python activity_spider.py
```

Set your Anthropic API key before running:
```bash
export ANTHROPIC_API_KEY=your_key_here
```

---

## How the Analysis Works

The system prompts Claude with:
- Top 50 markets by volume for the tag
- Top 10 biggest weekly movers (sorted by absolute week-over-week change)
- Prices expressed as probabilities (0.36 = 36%)
- Day, week, and month price changes

Claude identifies dominant themes, names sections after them, and always closes with **"Key Shifts This Week"** — the biggest movers regardless of topic.

**Example from iran report:**
> "US forces enter Iran by December 31" dropped 13.5pp to 65% — by far the week's largest move, indicating a significant deflation of the maximum-escalation scenario.

---

## Activity Spider

A separate module (`activity_spider.py`) continuously collects large trades (>$10,000 USD) from Polymarket's trade API and stores them in MySQL. Features:

- Deduplication by transaction hash
- Sports trade detection via regex pattern matching
- Incremental updates (only fetches new trades since last run)
- Trader metadata (pseudonym, bio, profile image)
