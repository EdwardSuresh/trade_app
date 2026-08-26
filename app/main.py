"""
main.py
-------
The FastAPI application itself. This file is deliberately short: it only

  1. creates the database tables,
  2. creates the app,
  3. plugs in the routes from app/routes/trades.py,
  4. serves the frontend folder.

The actual endpoints live in app/routes/trades.py.

Run it with:
    uvicorn app.main:app --reload

Then open:
    http://127.0.0.1:8000        -> the web page (frontend/index.html)
    http://127.0.0.1:8000/docs   -> automatic interactive API documentation
"""

from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.database import init_db
from app.routes import trades

# ---------------------------------------------------------------------------
# 1. Create the database tables (does nothing if they already exist)
# ---------------------------------------------------------------------------
init_db()

# ---------------------------------------------------------------------------
# 2. The application
# ---------------------------------------------------------------------------
app = FastAPI(
    title="Trade Station API",
    description="A tiny virtual stock-trading API: accounts, trades and portfolios.",
    version="1.0.0",
)

# ---------------------------------------------------------------------------
# 3. Plug in all the endpoints defined in app/routes/trades.py
# ---------------------------------------------------------------------------
app.include_router(trades.router)

# ---------------------------------------------------------------------------
# 4. Serve the frontend
# ---------------------------------------------------------------------------
# This MUST come last: it takes over the "/" path, and everything registered
# before it (all /api routes plus /docs) keeps working.
# html=True makes "/" serve frontend/index.html automatically.
FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"
app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
