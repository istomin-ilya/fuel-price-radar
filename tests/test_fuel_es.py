import gzip
import json
from decimal import Decimal
from pathlib import Path

import httpx
import pytest

from pipeline.collectors.fuel_es import collect, iter_products, parse_price

FIXTURE = Path(__file__).parent / "fixtures" / "fuel_es_sample.json"


@pytest.fixture
def payload():
    return json.loads(FIXTURE.read_text())


def test_parse_price_comma_decimal():
    assert parse_price("1,479") == Decimal("1.479")


def test_parse_price_blank_means_no_price():
    assert parse_price("") is None
    assert parse_price("   ") is None


def test_parse_price_garbage_raises():
    with pytest.raises(ValueError):
        parse_price("n/a")


def test_iter_products_one_per_station_fuel_with_price(payload):
    products = list(iter_products(payload))
    # 6 fixture stations: 3+2+1+1+3+3 fuels with prices
    assert len(products) == 13


def test_iter_products_skips_missing_fuels(payload):
    ids = {p["external_id"] for p in iter_products(payload)}
    assert "4375:g95" in ids
    assert "4375:diesel" in ids
    assert "4375:g98" not in ids  # station 4375 sells no G98


def test_iter_products_values(payload):
    by_id = {p["external_id"]: p for p in iter_products(payload)}
    p = by_id["4375:g95"]
    assert p["price_eur"] == Decimal("1.489")
    assert p["category"] == "g95"
    assert p["attrs"]["province"] == "ALBACETE"
    assert p["attrs"]["lat"] == pytest.approx(39.211417)


def test_collect_stores_response_verbatim(tmp_path):
    body = FIXTURE.read_bytes()

    def handler(request):
        return httpx.Response(200, content=body)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    path = collect(tmp_path, client=client)

    assert path == tmp_path / "fuel_es.json.gz"
    assert gzip.decompress(path.read_bytes()) == body
