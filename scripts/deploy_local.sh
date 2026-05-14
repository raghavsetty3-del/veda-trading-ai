#!/usr/bin/env bash
set -euo pipefail
if [ ! -f .env ]; then cp .env.example .env; echo "Created .env. Review before production."; fi
docker compose up --build -d
docker compose ps
