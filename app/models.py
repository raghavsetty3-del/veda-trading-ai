from datetime import datetime
from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db import Base


class AuditLog(Base):
    __tablename__ = "audit_logs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    event_type: Mapped[str] = mapped_column(String(100), index=True)
    entity_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    entity_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    severity: Mapped[str] = mapped_column(String(20), default="INFO")
    message: Mapped[str] = mapped_column(Text)
    payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)


class SourceDocument(Base):
    __tablename__ = "source_documents"
    __table_args__ = (UniqueConstraint("source_type", "source_url", name="uq_source_type_url"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_type: Mapped[str] = mapped_column(String(50), index=True)  # blog, telegram, x, pdf
    source_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_external_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    title: Mapped[str | None] = mapped_column(Text, nullable=True)
    author: Mapped[str | None] = mapped_column(String(255), nullable=True)
    raw_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_html: Mapped[str | None] = mapped_column(Text, nullable=True)
    media_paths: Mapped[list | None] = mapped_column(JSON, nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    ingested_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    processed: Mapped[bool] = mapped_column(Boolean, default=False)


class AuthorPrinciple(Base):
    __tablename__ = "author_principles"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    title: Mapped[str] = mapped_column(String(255))
    description: Mapped[str] = mapped_column(Text)
    source_type: Mapped[str] = mapped_column(String(50), default="book")
    source_ref: Mapped[str | None] = mapped_column(String(255), nullable=True)
    immutable: Mapped[bool] = mapped_column(Boolean, default=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class RuleMapping(Base):
    __tablename__ = "rule_mappings"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    principle_id: Mapped[int] = mapped_column(ForeignKey("author_principles.id"))
    rule_code: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    rule_name: Mapped[str] = mapped_column(String(255))
    logic_json: Mapped[dict] = mapped_column(JSON)
    expected_behavior: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(50), default="draft")
    version: Mapped[str] = mapped_column(String(50), default="0.1.0")
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    principle = relationship("AuthorPrinciple")


class ExtractedInsight(Base):
    __tablename__ = "extracted_insights"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_document_id: Mapped[int | None] = mapped_column(ForeignKey("source_documents.id"), nullable=True)
    bias: Mapped[str | None] = mapped_column(String(50), nullable=True)
    timeframe: Mapped[str | None] = mapped_column(String(50), nullable=True)
    symbols: Mapped[list | None] = mapped_column(JSON, nullable=True)
    concepts: Mapped[list | None] = mapped_column(JSON, nullable=True)
    psychology: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    expected_conditions: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    extraction_version: Mapped[str] = mapped_column(String(50), default="0.2.0")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class ValidationCase(Base):
    __tablename__ = "validation_cases"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    case_code: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    title: Mapped[str] = mapped_column(String(255))
    principle_id: Mapped[int | None] = mapped_column(ForeignKey("author_principles.id"), nullable=True)
    rule_id: Mapped[int | None] = mapped_column(ForeignKey("rule_mappings.id"), nullable=True)
    source_document_id: Mapped[int | None] = mapped_column(ForeignKey("source_documents.id"), nullable=True)
    expected_json: Mapped[dict] = mapped_column(JSON)
    delivered_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(String(50), default="pending")  # pending, pass, fail, partial
    score: Mapped[float | None] = mapped_column(Float, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    evaluated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class StrategyVersion(Base):
    __tablename__ = "strategy_versions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    strategy_code: Mapped[str] = mapped_column(String(100), index=True)
    version: Mapped[str] = mapped_column(String(50))
    config_json: Mapped[dict] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(50), default="draft")
    approved: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class MarketCandle(Base):
    __tablename__ = "market_candles"
    __table_args__ = (UniqueConstraint("symbol", "timeframe", "ts", name="uq_market_candle"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    symbol: Mapped[str] = mapped_column(String(50), index=True)
    timeframe: Mapped[str] = mapped_column(String(20), index=True)
    ts: Mapped[datetime] = mapped_column(DateTime, index=True)
    open: Mapped[float] = mapped_column(Float)
    high: Mapped[float] = mapped_column(Float)
    low: Mapped[float] = mapped_column(Float)
    close: Mapped[float] = mapped_column(Float)
    volume: Mapped[float | None] = mapped_column(Float, nullable=True)
    source: Mapped[str] = mapped_column(String(100), default="manual")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class PaperTrade(Base):
    __tablename__ = "paper_trades"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    symbol: Mapped[str] = mapped_column(String(50), index=True)
    timeframe: Mapped[str] = mapped_column(String(20), default="5m")
    side: Mapped[str] = mapped_column(String(20), index=True)
    stance: Mapped[str] = mapped_column(String(50), index=True)
    entry_price: Mapped[float] = mapped_column(Float)
    stop_loss: Mapped[float | None] = mapped_column(Float, nullable=True)
    target: Mapped[float | None] = mapped_column(Float, nullable=True)
    quantity: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[str] = mapped_column(String(50), default="planned", index=True)
    reason: Mapped[str] = mapped_column(Text)
    context: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)


class FailedJob(Base):
    __tablename__ = "failed_jobs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    job_type: Mapped[str] = mapped_column(String(100), index=True)
    payload: Mapped[dict] = mapped_column(JSON)
    error: Mapped[str] = mapped_column(Text)
    attempts: Mapped[int] = mapped_column(Integer, default=1)
    resolved: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class SystemState(Base):
    __tablename__ = "system_state"
    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    value: Mapped[dict] = mapped_column(JSON)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
