import os

import pytest
from sqlalchemy import create_engine, inspect

pytestmark = pytest.mark.skipif(
    "DATABASE_URL" not in os.environ, reason="needs a database"
)


def test_all_tables_exist():
    engine = create_engine(os.environ["DATABASE_URL"])
    tables = set(inspect(engine).get_table_names())
    assert {"sources", "products", "price_snapshots", "runs"} <= tables
