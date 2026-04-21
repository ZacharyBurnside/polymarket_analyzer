import json
import os
import sys
from datetime import datetime
from scraper import scrape_polymarket_events
from analysis import analyze, extract_markets

BASE = os.path.dirname(os.path.abspath(__file__))


def run(tag_slug: str = 'iran'):
    output_file = os.path.join(BASE, f'report_{tag_slug}.json')

    print(f"[{datetime.utcnow()}] Starting pipeline for tag: '{tag_slug}'")

    try:
        df = scrape_polymarket_events(tag_slug=tag_slug)
        print(f"[{datetime.utcnow()}] Scraped {len(df)} events")
    except Exception as e:
        print(f"ERROR during scraping: {e}")
        sys.exit(1)

    if df.empty:
        print("No data returned. Exiting.")
        sys.exit(1)

    try:
        result = analyze(df, tag_slug=tag_slug)
        print(f"[{datetime.utcnow()}] Analysis complete — "
              f"{result['input_tokens']} in / {result['output_tokens']} out tokens")
    except Exception as e:
        print(f"ERROR during analysis: {e}")
        sys.exit(1)

    result['markets'] = extract_markets(df)[:20]

    with open(output_file, 'w') as f:
        json.dump(result, f, indent=2)

    print(f"[{datetime.utcnow()}] Report saved to {output_file}")


if __name__ == "__main__":
    tag = sys.argv[1] if len(sys.argv) > 1 else 'iran'
    run(tag_slug=tag)