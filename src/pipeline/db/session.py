import os
from functools import lru_cache

from dotenv import load_dotenv
from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

load_dotenv()


@lru_cache(maxsize=1)
def get_engine() -> Engine:
    return create_engine(os.environ["DATABASE_URL"])


def make_session() -> Session:
    return sessionmaker(bind=get_engine())()
