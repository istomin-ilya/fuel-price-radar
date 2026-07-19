import gzip
import json
from datetime import UTC, date, datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from pipeline.collectors import fuel_es
from pipeline.db.models import PriceSnapshot, Product, Run, Source

BATCH = 1000


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


def load_fuel_es(session: Session, payload: dict, collected_at: date) -> tuple[int, int]:
    """Upsert products and their daily snapshots; returns (ok, failed)."""
    source = ensure_source(session, "fuel_es", "api", fuel_es.API_URL)
    products = list(fuel_es.iter_products(payload))

    prod_rows = [
        {
            "source_id": source.id,
            "external_id": p["external_id"],
            "title": p["title"],
            "category": p["category"],
            "attrs": p["attrs"],
        }
        for p in products
    ]
    for batch in _chunks(prod_rows):
        stmt = insert(Product).values(batch)
        stmt = stmt.on_conflict_do_update(
            index_elements=[Product.source_id, Product.external_id],
            set_={"title": stmt.excluded.title, "attrs": stmt.excluded.attrs},
        )
        session.execute(stmt)

    id_by_ext = dict(
        session.execute(
            select(Product.external_id, Product.id).where(Product.source_id == source.id)
        ).all()
    )
    snap_rows = [
        {
            "product_id": id_by_ext[p["external_id"]],
            "collected_at": collected_at,
            "price_eur": p["price_eur"],
            "is_available": True,
        }
        for p in products
    ]
    for batch in _chunks(snap_rows):
        stmt = insert(PriceSnapshot).values(batch)
        stmt = stmt.on_conflict_do_update(
            index_elements=[PriceSnapshot.product_id, PriceSnapshot.collected_at],
            set_={"price_eur": stmt.excluded.price_eur},
        )
        session.execute(stmt)

    return len(products), 0


def load_raw_dir(session: Session, day_dir: Path) -> Run | None:
    """Load one data/raw/YYYY-MM-DD/ directory, logging a Run per source."""
    collected_at = date.fromisoformat(day_dir.name)
    path = day_dir / "fuel_es.json.gz"
    if not path.exists():
        return None

    source = ensure_source(session, "fuel_es", "api", fuel_es.API_URL)
    run = Run(source_id=source.id, started_at=datetime.now(UTC), status="running")
    session.add(run)
    session.flush()
    try:
        payload = json.loads(gzip.decompress(path.read_bytes()))
        run.items_ok, run.items_failed = load_fuel_es(session, payload, collected_at)
        run.status = "ok"
    except Exception:
        run.status = "failed"
        raise
    finally:
        run.finished_at = datetime.now(UTC)
    return run
