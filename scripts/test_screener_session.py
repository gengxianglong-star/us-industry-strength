import re
import time

import requests
from bs4 import BeautifulSoup

session = requests.Session()
session.headers.update(
    {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    }
)

# warm up session
home = session.get("https://finviz.com/screener.ashx", timeout=30)
print("home", home.status_code, len(home.text))
time.sleep(1)

url = "https://finviz.com/screener.ashx?v=111&f=ind_semiconductors,ta_sma20_pa"
r = session.get(url, timeout=30)
print("screener", r.status_code, len(r.text))
tickers = sorted(set(re.findall(r"quote\.ashx\?t=([A-Z0-9.-]+)", r.text)))
print("tickers", len(tickers), tickers[:15])
print(r.text[:500])
