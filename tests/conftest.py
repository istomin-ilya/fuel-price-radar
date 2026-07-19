import os
from uuid import uuid4

import pytest
from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from pipeline.db.models import Base

load_dotenv()


@pytest.fixture
def session():
    """Fresh throwaway Postgres schema per test: full isolation from real data."""
    if "DATABASE_URL" not in os.environ:
        pytest.skip("needs a database")
    url = os.environ["DATABASE_URL"]
    schema = f"test_{uuid4().hex[:8]}"
    admin = create_engine(url)
    with admin.begin() as conn:
        conn.execute(text(f'CREATE SCHEMA "{schema}"'))

    engine = create_engine(url, connect_args={"options": f"-csearch_path={schema}"})
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session
    engine.dispose()

    with admin.begin() as conn:
        conn.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
    admin.dispose()
