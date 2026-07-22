import json
from datetime import date
from decimal import Decimal
from pathlib import Path

from sqlalchemy import text

from pipeline.load import load_eu_bulletin, load_fuel_es

FIXTURES = Path(__file__).parent / "fixtures"
MARTS = Path(__file__).parent.parent / "sql" / "marts"


def apply_marts(session):
    for sql_file in sorted(MARTS.glob("*.sql")):
        session.execute(text(sql_file.read_text()))


def test_price_history_combines_both_sources(session):
    payload = json.loads((FIXTURES / "fuel_es_sample.json").read_text())
    load_fuel_es(session, payload, date(2026, 7, 19))
    load_eu_bulletin(session, FIXTURES / "eu_bulletin_history_sample.xlsx")
    apply_marts(session)

    rows = session.execute(
        text("SELECT series, country, category, price_eur FROM mart_price_history")
    ).all()
    series = {r.series for r in rows}
    assert series == {"es_stations", "eu_bulletin"}

    es_daily = [r for r in rows if r.series == "es_stations" and r.category == "g95"]
    assert len(es_daily) == 1  # one day loaded -> one averaged point
    # fixture g95 prices: 1.599, 1.489, 1.559, 1.709, 1.669 -> avg 1.605
    assert es_daily[0].price_eur == Decimal("1.605")

    bulletin_es = [
        r for r in rows
        if r.series == "eu_bulletin" and r.country == "ES" and r.category == "g95"
    ]
    assert len(bulletin_es) == 12  # 12 weeks in the fixture


def test_regional_spread_slices_by_province_and_brand(session):
    payload = json.loads((FIXTURES / "fuel_es_sample.json").read_text())
    load_fuel_es(session, payload, date(2026, 7, 19))
    apply_marts(session)

    rows = session.execute(
        text(
            "SELECT dimension, name, avg_price_eur, n_stations "
            "FROM mart_regional_spread WHERE category = 'g95'"
        )
    ).all()

    by_dim_name = {(r.dimension, r.name): r for r in rows}
    # ALBACETE g95 stations in the fixture: 1.599, 1.489, 1.669 -> avg 1.586
    albacete = by_dim_name[("province", "ALBACETE")]
    assert albacete.avg_price_eur == Decimal("1.586")
    assert albacete.n_stations == 3

    repsol = by_dim_name[("brand", "REPSOL")]
    assert repsol.avg_price_eur == Decimal("1.709")
    assert repsol.n_stations == 1


def test_spain_vs_eu_tax_share(session):
    load_eu_bulletin(session, FIXTURES / "eu_bulletin_history_sample.xlsx")
    apply_marts(session)

    rows = session.execute(
        text(
            "SELECT country, price_eur, price_pre_tax_eur, tax_share "
            "FROM mart_spain_vs_eu WHERE week = '2026-07-13' AND category = 'g95'"
        )
    ).all()

    assert {r.country for r in rows} == {"ES", "FR", "PT", "IT", "DE", "EU"}
    es = next(r for r in rows if r.country == "ES")
    assert es.price_eur == Decimal("1.542")
    # (1.542 - 0.951) / 1.542 = 0.383 — taxes are ~38% of the pump price
    assert es.tax_share == Decimal("0.383")
