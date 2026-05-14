from pydantic import BaseModel, Field
from datetime import datetime


class PrincipleCreate(BaseModel):
    code: str
    title: str
    description: str
    source_type: str = "book"
    source_ref: str | None = None
    immutable: bool = True


class RuleMappingCreate(BaseModel):
    principle_id: int
    rule_code: str
    rule_name: str
    logic_json: dict
    expected_behavior: str
    status: str = "draft"
    version: str = "0.1.0"


class RuleActivationRequest(BaseModel):
    active: bool
    validation_note: str = Field(min_length=10)


class RuleEvaluationRequest(BaseModel):
    market_context: dict


class SetupEvaluationRequest(BaseModel):
    market_context: dict


class MarketCandleCreate(BaseModel):
    symbol: str
    timeframe: str = "5m"
    ts: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float | None = None
    source: str = "manual"


class MarketCandleBulkCreate(BaseModel):
    candles: list[MarketCandleCreate]


class MarketSnapshotRequest(BaseModel):
    symbol: str
    timeframe: str = "5m"
    limit: int = 50


class PaperTradeRequest(BaseModel):
    symbol: str
    timeframe: str = "5m"
    market_context: dict
    quantity: int = 1
    allow_when_kill_switch_on: bool = False


class PaperTradeStatusUpdate(BaseModel):
    status: str


class PaperSchedulerRunRequest(BaseModel):
    symbols: list[str] | None = None
    timeframe: str | None = None
    limit: int | None = None
    quantity: int | None = None


class BacktestStep(BaseModel):
    label: str | None = None
    market_context: dict


class BacktestRequest(BaseModel):
    name: str = "manual-backtest"
    symbol: str
    timeframe: str = "5m"
    steps: list[BacktestStep]


class CandleBacktestRequest(BaseModel):
    name: str = "stored-candle-replay"
    symbol: str
    timeframe: str = "5m"
    limit: int = 200
    min_window: int = 20


class RuleSuggestionPromotionRequest(BaseModel):
    review_note: str | None = None


class SourceDocumentCreate(BaseModel):
    source_type: str
    source_url: str | None = None
    source_external_id: str | None = None
    title: str | None = None
    author: str | None = None
    raw_text: str | None = None
    raw_html: str | None = None
    media_paths: list[str] | None = None


class TelegramExportMessage(BaseModel):
    message_id: str | int
    text: str
    date: str | None = None
    author: str | None = None
    media_paths: list[str] | None = None


class TelegramExportIngestRequest(BaseModel):
    channel: str
    messages: list[TelegramExportMessage]


class ValidationCaseCreate(BaseModel):
    case_code: str
    title: str
    principle_id: int | None = None
    rule_id: int | None = None
    source_document_id: int | None = None
    expected_json: dict
    notes: str | None = None


class ValidationResultUpdate(BaseModel):
    delivered_json: dict
    status: str
    score: float | None = None
    notes: str | None = None


class AuditEvent(BaseModel):
    event_type: str
    entity_type: str | None = None
    entity_id: str | None = None
    severity: str = "INFO"
    message: str
    payload: dict | None = None
