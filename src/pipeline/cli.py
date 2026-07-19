import argparse
from datetime import UTC, datetime
from pathlib import Path

from pipeline.collectors import fuel_es

RAW_ROOT = Path("data/raw")


def cmd_collect(_args: argparse.Namespace) -> None:
    day_dir = RAW_ROOT / datetime.now(UTC).strftime("%Y-%m-%d")
    path = fuel_es.collect(day_dir)
    size_kb = path.stat().st_size / 1024
    print(f"saved {path} ({size_kb:.0f} KiB)")


def cmd_load(_args: argparse.Namespace) -> None:
    from pipeline.db.session import make_session
    from pipeline.load import load_raw_dir

    session = make_session()
    try:
        for day_dir in sorted(p for p in RAW_ROOT.iterdir() if p.is_dir()):
            run = load_raw_dir(session, day_dir)
            session.commit()
            if run is not None:
                print(f"{day_dir.name}: {run.status}, ok={run.items_ok} failed={run.items_failed}")
    finally:
        session.close()


def main() -> None:
    parser = argparse.ArgumentParser(prog="pipeline", description="Fuel Price Radar pipeline")
    sub = parser.add_subparsers(dest="command", required=True)

    p_collect = sub.add_parser("collect", help="fetch raw snapshots from all sources")
    p_collect.set_defaults(func=cmd_collect)

    p_load = sub.add_parser("load", help="upsert raw snapshots into Postgres")
    p_load.set_defaults(func=cmd_load)

    args = parser.parse_args()
    args.func(args)
