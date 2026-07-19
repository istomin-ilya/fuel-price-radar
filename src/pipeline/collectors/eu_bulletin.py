import re
import time
import urllib.robotparser
from collections.abc import Iterator
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from urllib.parse import urljoin

import httpx
import pandas as pd
from bs4 import BeautifulSoup

from pipeline.collectors.base import USER_AGENT, polite_get

BASE_URL = "https://energy.ec.europa.eu"
PAGE_URL = f"{BASE_URL}/data-and-analysis/weekly-oil-bulletin_en"
ROBOTS_URL = f"{BASE_URL}/robots.txt"
HISTORY_MARKER = "Prices_History"
HISTORY_FILENAME = "eu_bulletin_history.xlsx"
REQUEST_PAUSE_S = 1.5

# ES_price_with_tax_euro95, EU_price_wo_tax_diesel, ...
# (matches 2-letter codes only, so the "EUR_" eurozone aggregate is skipped)
_HEADER_RE = re.compile(r"^([A-Z]{2})_price_(with|wo)_tax_(euro95|diesel)$")
_FUEL_BY_SUFFIX = {"euro95": "g95", "diesel": "diesel"}
_SHEET_BY_KIND = {"with_tax": "Prices with taxes", "wo_tax": "Prices wo taxes"}
_PER_LITRE = Decimal("0.001")  # sheet prices are per 1000 l


def check_robots(*, client: httpx.Client | None = None) -> bool:
    resp = polite_get(ROBOTS_URL, client=client)
    parser = urllib.robotparser.RobotFileParser()
    parser.parse(resp.text.splitlines())
    return parser.can_fetch(USER_AGENT, PAGE_URL)


def find_history_url(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for a in soup.find_all("a", href=True):
        if HISTORY_MARKER in a["href"]:
            return urljoin(BASE_URL, a["href"])
    raise ValueError("history workbook link not found on the bulletin page")


def parse_history_xlsx(path: Path) -> Iterator[dict]:
    """Yield one record per country x fuel x week x tax-kind.

    The sheets are wide: one column block per country, blocks vary in width
    (non-euro countries carry an extra exchange-rate column), so columns are
    located by header name, never by position. Footer disclaimers have no
    date in column 0 and are skipped.
    """
    for kind, sheet in _SHEET_BY_KIND.items():
        df = pd.read_excel(path, sheet_name=sheet, header=None)
        price_cols = []
        for col_idx, name in df.iloc[0].items():
            if isinstance(name, str) and (m := _HEADER_RE.match(name)):
                price_cols.append((col_idx, m.group(1), _FUEL_BY_SUFFIX[m.group(3)]))

        for _, row in df.iloc[3:].iterrows():
            week = row.iloc[0]
            if not isinstance(week, datetime | pd.Timestamp):
                continue
            for col_idx, country, fuel in price_cols:
                value = row.iloc[col_idx]
                if not isinstance(value, int | float) or pd.isna(value):
                    continue
                yield {
                    "country": country,
                    "category": fuel,
                    "week": week.date(),
                    "price_kind": kind,
                    "price_per_litre": (Decimal(str(value)) * _PER_LITRE).quantize(
                        Decimal("0.001")
                    ),
                }


def collect(out_dir: Path, *, client: httpx.Client | None = None) -> Path:
    """robots check -> bulletin page -> download the consolidated history file."""
    if not check_robots(client=client):
        raise RuntimeError("robots.txt disallows fetching the bulletin page")
    time.sleep(REQUEST_PAUSE_S)
    page = polite_get(PAGE_URL, client=client)
    history_url = find_history_url(page.text)
    time.sleep(REQUEST_PAUSE_S)
    resp = polite_get(history_url, client=client)

    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / HISTORY_FILENAME
    path.write_bytes(resp.content)  # xlsx is already a zip container, no gzip
    return path
