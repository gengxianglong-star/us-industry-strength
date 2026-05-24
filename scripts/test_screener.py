import re
import requests
from bs4 import BeautifulSoup

headers = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://finviz.com/screener.ashx",
}

filters_list = [
    "ind_semiconductors,ta_sma20_pa",
    "ind_semiconductors,ta_sma20_pa,ta_sma20_sb50",
    "ind_semiconductors,ta_sma20_pa,ta_sma20_sb50,sh_curvol_o10M",
    "ind_semiconductors,ta_sma20_pa,ta_sma20_sb50,sh_curvol_o10",
    "ind_semiconductors,ta_sma20_pa,ta_sma20_sb50,sh_curvol_o10000000",
]

for f in filters_list:
    url = f"https://finviz.com/screener.ashx?v=111&f={f}"
    r = requests.get(url, headers=headers, timeout=30)
    tickers = sorted(set(re.findall(r"quote\.ashx\?t=([A-Z0-9.-]+)", r.text)))
    total = re.search(r"#(\d+) / (\d+) Total", r.text)
    print(f"\nstatus={r.status_code} f={f}")
    print(" total:", total.group(0) if total else None)
    print(" tickers:", len(tickers), tickers[:12])
