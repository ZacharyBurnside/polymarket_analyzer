import requests
import pandas as pd
import time


HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
    'Accept': 'application/json, text/plain, */*',
    'Accept-Language': 'en-US,en;q=0.9',
    'Referer': 'https://polymarket.com/',
    'Origin': 'https://polymarket.com',
}

def scrape_polymarket_events(
    tag_slug='iran',
    limit=20,
    delay=0.5
):
    base_url = 'https://gamma-api.polymarket.com/events/pagination'
    all_data = []
    offset = 0

    params = {
        'limit': limit,
        'active': 'true',
        'archived': 'false',
        'tag_slug': tag_slug,
        'closed': 'false',
        'order': 'volume24hr',
        'ascending': 'false',
    }

    while True:
        params['offset'] = offset
        response = requests.get(base_url, params=params, headers = HEADERS, timeout=10)
        response.raise_for_status()
        results = response.json()

        data = results.get('data', [])
        if not data:
            break

        all_data.extend(data)

        total = results.get('count', None)
        if total is not None and len(all_data) >= total:
            break
        if len(data) < limit:
            break

        offset += limit
        time.sleep(delay)

    return pd.DataFrame(all_data) if all_data else pd.DataFrame()