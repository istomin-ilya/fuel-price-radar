import argparse
from datetime import UTC, datetime
from pathlib import Path

from pipeline.collectors import eu_bulletin, fuel_es

RAW_ROOT = Path("data/raw")


def cmd_collect(_args: argparse.Namespace) -> None:
    day_dir = RAW_ROOT / datetime.now(UTC).strftime("%Y-%m-%d")
    for collector in (fuel_es, eu_bulletin):
        path = collector.collect(day_dir)
        size_kb = path.stat().st_size / 1024
        print(f"saved {path} ({size_kb:.0f} KiB)")


def cmd_load(_args: argparse.Namespace) -> None:
    from pipeline.db.session import make_session
    from pipeline.load import load_raw_dir

    session = make_session()
    try:
        for day_dir in sorted(p for p in RAW_ROOT.iterdir() if p.is_dir()):
            runs = load_raw_dir(session, day_dir)
            session.commit()
            for run in runs:
                print(
                    f"{day_dir.name} source={run.source_id}: {run.status}, "
                    f"ok={run.items_ok} failed={run.items_failed}"
                )
    finally:
        session.close()


def cmd_marts(_args: argparse.Namespace) -> None:
    from sqlalchemy import text

    from pipeline.db.session import make_session

    session = make_session()
    try:
        for sql_file in sorted(Path("sql/marts").glob("*.sql")):
            session.execute(text(sql_file.read_text()))
            print(f"applied {sql_file.name}")
        session.commit()
    finally:
        session.close()


def cmd_site(_args: argparse.Namespace) -> None:
    from pipeline.site import build

    index = build(Path("site"))
    print(f"built {index}")


def main() -> None:
    parser = argparse.ArgumentParser(prog="pipeline", description="Fuel Price Radar pipeline")
    sub = parser.add_subparsers(dest="command", required=True)

    p_collect = sub.add_parser("collect", help="fetch raw snapshots from all sources")
    p_collect.set_defaults(func=cmd_collect)

    p_load = sub.add_parser("load", help="upsert raw snapshots into Postgres")
    p_load.set_defaults(func=cmd_load)

    p_marts = sub.add_parser("marts", help="create or refresh SQL mart views")
    p_marts.set_defaults(func=cmd_marts)

    p_site = sub.add_parser("site", help="render the static status page into site/")
    p_site.set_defaults(func=cmd_site)

    args = parser.parse_args()
    args.func(args)
