from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Source(Base):
    __tablename__ = "sources"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True)
    kind: Mapped[str] = mapped_column(String(10))  # "api" | "html"
    base_url: Mapped[str] = mapped_column(String(500))

    products: Mapped[list[Product]] = relationship(back_populates="source")


class Product(Base):
    """One priced item: a station x fuel type, or a country x fuel type."""

    __tablename__ = "products"
    __table_args__ = (UniqueConstraint("source_id", "external_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("sources.id"))
    external_id: Mapped[str] = mapped_column(String(100))
    title: Mapped[str] = mapped_column(Text)
    category: Mapped[str] = mapped_column(String(50))
    url: Mapped[str | None] = mapped_column(String(500))
    attrs: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    source: Mapped[Source] = relationship(back_populates="products")


class PriceSnapshot(Base):
    __tablename__ = "price_snapshots"
    __table_args__ = (UniqueConstraint("product_id", "collected_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"))
    collected_at: Mapped[date] = mapped_column(Date)
    price_eur: Mapped[Decimal] = mapped_column(Numeric(10, 3))
    price_pre_tax_eur: Mapped[Decimal | None] = mapped_column(Numeric(10, 3))
    is_available: Mapped[bool] = mapped_column(Boolean, default=True)


class Run(Base):
    __tablename__ = "runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("sources.id"))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    items_ok: Mapped[int] = mapped_column(default=0)
    items_failed: Mapped[int] = mapped_column(default=0)
    status: Mapped[str] = mapped_column(String(20))  # "ok" | "failed"
