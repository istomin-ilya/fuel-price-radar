import gzip
import json
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import func, select

from pipeline.db.models import PriceSnapshot, Product
from pipeline.load import load_eu_bulletin, load_fuel_es, load_raw_dir

FIXTURE = Path(__file__).parent / "fixtures" / "fuel_es_sample.json"
BULLETIN_FIXTURE = Path(__file__).parent / "fixtures" / "eu_bulletin_history_sample.xlsx"
DAY = date(2026, 7, 19)


@pytest.fixture
def payload():
    return json.loads(FIXTURE.read_text())


def count(session, model):
    return session.scalar(select(func.count()).select_from(model))


def test_first_load_inserts_everything(session, payload):
    ok, failed = load_fuel_es(session, payload, DAY)
    assert (ok, failed) == (13, 0)
    assert count(session, Product) == 13
    assert count(session, PriceSnapshot) == 13


def test_reload_same_day_is_idempotent(session, payload):
    load_fuel_es(session, payload, DAY)
    load_fuel_es(session, payload, DAY)
    assert count(session, Product) == 13
    assert count(session, PriceSnapshot) == 13


def test_reload_updates_price_without_duplicates(session, payload):
    load_fuel_es(session, payload, DAY)
    payload["ListaEESSPrecio"][1]["Precio Gasolina 95 E5"] = "1,999"
    load_fuel_es(session, payload, DAY)

    station_id = payload["ListaEESSPrecio"][1]["IDEESS"]
    product = session.scalar(
        select(Product).where(Product.external_id == f"{station_id}:g95")
    )
    snap = session.scalar(
        select(PriceSnapshot).where(PriceSnapshot.product_id == product.id)
    )
    assert snap.price_eur == Decimal("1.999")
    assert count(session, PriceSnapshot) == 13


def test_next_day_adds_new_snapshots_not_products(session, payload):
    load_fuel_es(session, payload, DAY)
    load_fuel_es(session, payload, date(2026, 7, 20))
    assert count(session, Product) == 13
    assert count(session, PriceSnapshot) == 26


def test_load_raw_dir_logs_run_per_source(session, payload, tmp_path):
    day_dir = tmp_path / "2026-07-19"
    day_dir.mkdir()
    (day_dir / "fuel_es.json.gz").write_bytes(
        gzip.compress(json.dumps(payload).encode())
    )
    (day_dir / "eu_bulletin_history.xlsx").write_bytes(BULLETIN_FIXTURE.read_bytes())

    runs = load_raw_dir(session, day_dir)

    assert len(runs) == 2
    assert all(r.status == "ok" and r.finished_at is not None for r in runs)
    assert runs[0].items_ok == 13  # fuel_es
    assert runs[1].items_ok > 0  # eu_bulletin


def test_load_eu_bulletin_known_week(session):
    ok, failed = load_eu_bulletin(session, BULLETIN_FIXTURE)
    assert ok > 0

    product = session.scalar(select(Product).where(Product.external_id == "ES:g95"))
    assert product.category == "g95"
    assert product.attrs == {"country": "ES"}

    snap = session.scalar(
        select(PriceSnapshot).where(
            PriceSnapshot.product_id == product.id,
            PriceSnapshot.collected_at == date(2026, 7, 13),
        )
    )
    assert snap.price_eur == Decimal("1.542")
    assert snap.price_pre_tax_eur == Decimal("0.951")


def test_load_eu_bulletin_idempotent(session):
    load_eu_bulletin(session, BULLETIN_FIXTURE)
    first = session.scalar(select(func.count()).select_from(PriceSnapshot))
    load_eu_bulletin(session, BULLETIN_FIXTURE)
    assert session.scalar(select(func.count()).select_from(PriceSnapshot)) == first
