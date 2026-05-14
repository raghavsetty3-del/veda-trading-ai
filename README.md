# Veda Trading AI v0.2

Modular, recoverable, author-aligned trading intelligence platform.

## v0.2 Additions

- Blog ingestion service
- Blog post parser
- Raw source archive model
- Expected vs delivered validation model
- Principle-to-rule-to-result traceability
- Dashboard pages:
  - Project health
  - Author principles
  - Rule mappings
  - Validation tracker
  - Ingestion status
  - Recovery controls
- Telegram/X ingestion placeholders ready for credentials
- Recovery-first architecture
- Live trading disabled by default

## Start

```bash
cp .env.example .env
docker compose up --build
```

API: http://localhost:8000  
Dashboard: http://localhost:8501
