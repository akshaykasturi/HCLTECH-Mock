"""Audit tables. Rows are only ever inserted: see app/db/repository.py."""
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import JSON, DateTime, Float, ForeignKey, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class Analysis(Base):
    """One row per /api/analyze call. Text columns hold redacted text only."""
    __tablename__ = "analyses"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)  # = AnalysisResult.analysis_id
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    request_id: Mapped[str] = mapped_column(String(100))
    title: Mapped[str] = mapped_column(Text)
    description: Mapped[str] = mapped_column(Text)
    category: Mapped[str] = mapped_column(String(100))
    subcategory: Mapped[str] = mapped_column(String(100))
    priority: Mapped[str] = mapped_column(String(10))
    classifier_confidence: Mapped[float] = mapped_column(Float)
    outcome: Mapped[str] = mapped_column(String(20), index=True)
    confidence: Mapped[float] = mapped_column(Float)
    reasons: Mapped[list[str]] = mapped_column(JSON)
    signals: Mapped[dict[str, float]] = mapped_column(JSON)
    recommendation: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, nullable=True)
    matches: Mapped[list[dict[str, Any]]] = mapped_column(JSON)
    trace: Mapped[list[dict[str, Any]]] = mapped_column(JSON)
    generator: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)  # None: gate stopped it


class Feedback(Base):
    """An analyst's verdict on an analysis's recommendation or on one of its matches."""
    __tablename__ = "feedback"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    analysis_id: Mapped[str] = mapped_column(ForeignKey("analyses.id"), index=True)
    verdict: Mapped[str] = mapped_column(String(20))
    target: Mapped[str] = mapped_column(String(120))
    comment: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    reviewer: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
