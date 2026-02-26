#!/usr/bin/env bash
# Run the FastAPI app using the project venv (no need to activate manually).
set -e
cd "$(dirname "$0")"
./venv/bin/uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
