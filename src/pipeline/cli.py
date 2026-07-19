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


def main() -> None:
    parser = argparse.ArgumentParser(prog="pipeline", description="Fuel Price Radar pipeline")
    sub = parser.add_subparsers(dest="command", required=True)

    p_collect = sub.add_parser("collect", help="fetch raw snapshots from all sources")
    p_collect.set_defaults(func=cmd_collect)

    args = parser.parse_args()
    args.func(args)
