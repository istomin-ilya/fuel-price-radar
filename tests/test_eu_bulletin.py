from datetime import date
from decimal import Decimal
from pathlib import Path

import httpx
import pytest

from pipeline.collectors import eu_bulletin
from pipeline.collectors.eu_bulletin import (
    check_robots,
    collect,
    find_history_url,
    parse_history_xlsx,
)

FIXTURES = Path(__file__).parent / "fixtures"
PAGE_HTML = (FIXTURES / "eu_bulletin_page.html").read_text()
HISTORY_XLSX = FIXTURES / "eu_bulletin_history_sample.xlsx"


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    monkeypatch.setattr(eu_bulletin.time, "sleep", lambda _: None)


def test_find_history_url_on_real_page():
    url = find_history_url(PAGE_HTML)
    assert url.startswith("https://energy.ec.europa.eu/")
    assert "Prices_History" in url


def test_find_history_url_missing_raises():
    with pytest.raises(ValueError):
        find_history_url("<html><body>no links here</body></html>")


def test_check_robots_allowed():
    robots = "User-agent: *\nDisallow: /admin/\n"
    client = httpx.Client(
        transport=httpx.MockTransport(lambda req: httpx.Response(200, text=robots))
    )
    assert check_robots(client=client) is True


def test_check_robots_disallowed():
    robots = "User-agent: *\nDisallow: /\n"
    client = httpx.Client(
        transport=httpx.MockTransport(lambda req: httpx.Response(200, text=robots))
    )
    assert check_robots(client=client) is False


def test_parse_history_known_values():
    records = list(parse_history_xlsx(HISTORY_XLSX))
    by_key = {
        (r["country"], r["category"], r["week"], r["price_kind"]): r["price_per_litre"]
        for r in records
    }
    # cross-checked by hand against the workbook, week of 2026-07-13
    week = date(2026, 7, 13)
    assert by_key[("ES", "g95", week, "with_tax")] == Decimal("1.542")
    assert by_key[("ES", "g95", week, "wo_tax")] == Decimal("0.951")
    assert by_key[("EU", "g95", week, "with_tax")] == Decimal("1.851")


def test_parse_history_shape():
    records = list(parse_history_xlsx(HISTORY_XLSX))
    countries = {r["country"] for r in records}
    assert {"ES", "FR", "PT", "IT", "DE", "EU"} <= countries
    assert "EUR" not in {r["country"] for r in records}  # aggregate block skipped
    weeks = {r["week"] for r in records}
    assert len(weeks) == 12  # fixture holds 12 data rows per sheet
    assert all(r["price_per_litre"] > 0 for r in records)


def test_collect_downloads_history_file(tmp_path):
    robots = "User-agent: *\nDisallow: /admin/\n"
    xlsx_bytes = HISTORY_XLSX.read_bytes()
    seen = []

    def handler(request):
        seen.append(str(request.url))
        if request.url.path.endswith("robots.txt"):
            return httpx.Response(200, text=robots)
        if "weekly-oil-bulletin" in request.url.path:
            return httpx.Response(200, text=PAGE_HTML)
        return httpx.Response(200, content=xlsx_bytes)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    path = collect(tmp_path, client=client)

    assert path.read_bytes() == xlsx_bytes
    assert len(seen) == 3  # robots, page, file — and nothing else
