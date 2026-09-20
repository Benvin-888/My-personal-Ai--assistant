# Phase 2.45 — MongoDB Persistence Layer

Adds real MongoDB persistence for APEX trade evidence.

## Configuration

Only `MONGODB_URI` is required. A local `.env` file is loaded with `python-dotenv` and is never committed because `.gitignore` excludes `.env` and `.env.*`.

The database name is taken from the URI path. If the URI has no database path, `benvin` is used.

## Safety

MongoDB is a persistence and research layer only. It cannot authorize, execute, modify, cancel, or risk-manage trades.
