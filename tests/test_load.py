import gzip
import json
import os
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from pipeline.db.models import PriceSnapshot, Product, Run
from pipeline.load import load_fuel_es, load_raw_dir

pytestmark = pytest.mark.skipif(
    "DATABASE_URL" not in os.environ, reason="needs a database"
)

FIXTURE = Path(__file__).parent / "fixtures" / "fuel_es_sample.json"
DAY = date(2026, 7, 19)


@pytest.fixture
def session():
    engine = create_engine(os.environ["DATABASE_URL"])
    conn = engine.connect()
    tx = conn.begin()
    session = Session(bind=conn)
    yield session
    session.close()
    tx.rollback()  # nothing this test did survives
    conn.close()


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


def test_load_raw_dir_logs_run(session, payload, tmp_path):
    day_dir = tmp_path / "2026-07-19"
    day_dir.mkdir()
    (day_dir / "fuel_es.json.gz").write_bytes(
        gzip.compress(json.dumps(payload).encode())
    )

    load_raw_dir(session, day_dir)

    run = session.scalar(select(Run))
    assert run.status == "ok"
    assert run.items_ok == 13
    assert run.finished_at is not None
