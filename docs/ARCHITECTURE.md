# Architecture

## v0.2 Principle

Modular monolith first. Split only when justified.

## Runtime

```text
Azure VM
├── Docker Compose
├── FastAPI API
├── Worker
├── Scheduler
├── Streamlit Dashboard
├── PostgreSQL
├── Redis
├── ChromaDB
└── Backup scripts
```

## Data Flow

```text
Blog/Telegram/X/PDF
↓
SourceDocument raw archive
↓
Psychology + knowledge extraction
↓
Author principles + rule mappings
↓
Validation cases
↓
Replay/backtest later
↓
Dashboard
```
