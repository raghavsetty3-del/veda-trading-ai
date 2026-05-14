# Veda Trading System Context

## Project Identity

- Project name: Veda Trading System / Veda Trading AI
- Repository: https://github.com/raghavsetty3-del/veda-trading-ai
- Local path: `C:\Users\LENOVO\Downloads\veda-trading-ai-v0.2`
- Deployed VM: `vm-ai-trading-india`
- Azure account used for deployment: `vnraghav@yahoo.com`
- Public VM IP: `20.235.64.162`
- Dashboard: http://20.235.64.162/
- API health: http://20.235.64.162/api/health

## Current Deployment

The running deployment uses the existing Azure VM rather than creating a new one. The stack runs from:

`/home/traderadmin/veda-trading-ai`

Running services:

- FastAPI API
- Streamlit dashboard
- PostgreSQL
- Redis
- ChromaDB
- Worker
- Scheduler
- Nginx front door

The older `ai-trading-bot` container was stopped to free port `8000`. Its SQLite database was backed up before replacement:

`/home/traderadmin/veda-backups/trading.db.before-v02-deploy.20260514_113047`

Network access is restricted in the Azure NSG to the then-current public IP `122.171.18.3/32` for the app ports.

## ChatGPT Project Extraction

ChatGPT project URL:

https://chatgpt.com/g/g-p-6a0550f6cce88191a531427635ea2f8a-veda-trading-system/project

Observed project state:

- Project title: `Veda trading system`
- Visible project chat: `Nifty Trading Analysis`
- Sources tab: empty at extraction time
- The project chat starts with the uploaded file prompt:
  - File: `Practical Guide to Trading and Investing by JustNifty.pdf`
  - User intent: analyze how it can be used for Nifty trading
- Later discussion in the same chat focused on GitHub authentication and pushing the project repository.

## Local Source Document

PDF path:

`C:\Users\LENOVO\Downloads\Practical Guide to Trading and Investing by JustNifty.pdf`

Extracted document metadata:

- Title: `Practical Guide to Trading and Investing`
- Author shown in document: VanIlango / JustNifty
- Pages: 154
- Extraction status: text extraction works

This project should treat the PDF as a copyrighted source. Store compact derived principles, rules, and validation cases rather than full-text reproduction.

## System Direction

Veda is intended to become a recoverable, author-aligned trading intelligence platform. The current v0.2 architecture should preserve:

- Raw source archive
- Author principles
- Rule mappings
- Expected-vs-delivered validation
- Audit trail
- Paper-first operation
- Live trading disabled by default
- Human approval before any live trading transition

## Immediate Next Context

The JustNifty PDF is the primary trading-method source to translate into Veda rules. The extracted Veda interpretation is maintained in:

`docs/JUSTNIFTY_VEDA_EXTRACTION.md`
