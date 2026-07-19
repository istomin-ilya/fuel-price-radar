import gzip
import json
from collections.abc import Callable
from datetime import UTC, date, datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from pipeline.collectors import eu_bulletin, fuel_es
from pipeline.db.models import PriceSnapshot, Product, Run, Source

BATCH = 1000

FUEL_TITLES = {"g95": "Euro-super 95", "diesel": "Automotive diesel"}


def _chunks(rows: list[dict], size: int = BATCH):
    for i in range(0, len(rows), size):
        yield rows[i : i + size]


def ensure_source(session: Session, name: str, kind: str, base_url: str) -> Source:
    source = session.scalar(select(Source).where(Source.name == name))
    if source is None:
        source = Source(name=name, kind=kind, base_url=base_url)
        session.add(source)
        session.flush()
    return source


def _upsert_products(session: Session, rows: list[dict]) -> None:
    for batch in _chunks(rows):
        stmt = insert(Product).values(batch)
        stmt = stmt.on_conflict_do_update(
            index_elements=[Product.source_id, Product.external_id],
            set_={"title": stmt.excluded.title, "attrs": stmt.excluded.attrs},
        )
        session.execute(stmt)


def _upsert_snapshots(session: Session, rows: list[dict]) -> None:
    for batch in _chunks(rows):
        stmt = insert(PriceSnapshot).values(batch)
        stmt = stmt.on_conflict_do_update(
            index_elements=[PriceSnapshot.product_id, PriceSnapshot.collected_at],
            set_={
                "price_eur": stmt.excluded.price_eur,
                "price_pre_tax_eur": stmt.excluded.price_pre_tax_eur,
            },
        )
        session.execute(stmt)


def _product_ids(session: Session, source: Source) -> dict[str, int]:
    return dict(
        session.execute(
            select(Product.external_id, Product.id).where(Product.source_id == source.id)
        ).all()
    )


def load_fuel_es(session: Session, payload: dict, collected_at: date) -> tuple[int, int]:
    """Upsert station x fuel products and their daily snapshots."""
    source = ensure_source(session, "fuel_es", "api", fuel_es.API_URL)
    products = list(fuel_es.iter_products(payload))

    _upsert_products(
        session,
        [
            {
                "source_id": source.id,
                "external_id": p["external_id"],
                "title": p["title"],
                "category": p["category"],
                "attrs": p["attrs"],
            }
            for p in products
        ],
    )
    id_by_ext = _product_ids(session, source)
    _upsert_snapshots(
        session,
        [
            {
                "product_id": id_by_ext[p["external_id"]],
                "collected_at": collected_at,
                "price_eur": p["price_eur"],
                "is_available": True,
            }
            for p in products
        ],
    )
    return len(products), 0


def load_eu_bulletin(session: Session, xlsx_path: Path) -> tuple[int, int]:
    """Upsert country x fuel products and weekly snapshots (pre-tax price too)."""
    source = ensure_source(session, "eu_bulletin", "html", eu_bulletin.PAGE_URL)

    merged: dict[tuple, dict] = {}
    for r in eu_bulletin.parse_history_xlsx(xlsx_path):
        key = (r["country"], r["category"], r["week"])
        merged.setdefault(key, {})[r["price_kind"]] = r["price_per_litre"]

    _upsert_products(
        session,
        [
            {
                "source_id": source.id,
                "external_id": f"{country}:{fuel}",
                "title": f"{country} — {FUEL_TITLES[fuel]}",
                "category": fuel,
                "attrs": {"country": country},
            }
            for country, fuel in sorted({(c, f) for c, f, _ in merged})
        ],
    )
    id_by_ext = _product_ids(session, source)

    snap_rows = []
    skipped = 0
    for (country, fuel, week), prices in merged.items():
        if "with_tax" not in prices:  # price_eur is NOT NULL by schema
            skipped += 1
            continue
        snap_rows.append(
            {
                "product_id": id_by_ext[f"{country}:{fuel}"],
                "collected_at": week,
                "price_eur": prices["with_tax"],
                "price_pre_tax_eur": prices.get("wo_tax"),
                "is_available": True,
            }
        )
    _upsert_snapshots(session, snap_rows)
    return len(snap_rows), skipped


def _logged_run(session: Session, source: Source, work: Callable[[], tuple[int, int]]) -> Run:
    run = Run(source_id=source.id, started_at=datetime.now(UTC), status="running")
    session.add(run)
    session.flush()
    try:
        run.items_ok, run.items_failed = work()
        run.status = "ok"
    except Exception:
        run.status = "failed"
        raise
    finally:
        run.finished_at = datetime.now(UTC)
    return run


def load_raw_dir(session: Session, day_dir: Path) -> list[Run]:
    """Load one data/raw/YYYY-MM-DD/ directory; one logged Run per source found."""
    collected_at = date.fromisoformat(day_dir.name)
    runs = []

    fuel_path = day_dir / "fuel_es.json.gz"
    if fuel_path.exists():
        source = ensure_source(session, "fuel_es", "api", fuel_es.API_URL)
        payload = json.loads(gzip.decompress(fuel_path.read_bytes()))
        runs.append(
            _logged_run(session, source, lambda: load_fuel_es(session, payload, collected_at))
        )

    bulletin_path = day_dir / eu_bulletin.HISTORY_FILENAME
    if bulletin_path.exists():
        source = ensure_source(session, "eu_bulletin", "html", eu_bulletin.PAGE_URL)
        runs.append(
            _logged_run(session, source, lambda: load_eu_bulletin(session, bulletin_path))
        )

    return runs
