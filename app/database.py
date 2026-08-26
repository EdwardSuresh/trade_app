"""
database.py
-----------
Everything related to the database connection lives here.

We use SQLite, which is just a single file on disk (trades.db).
No database server to install - perfect for learning.
"""

from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

# ---------------------------------------------------------------------------
# 1. Where is the database file?
# ---------------------------------------------------------------------------
# Path(__file__) is ".../trade_app/app/database.py"
# .resolve().parent          -> ".../trade_app/app"
# .parent                    -> ".../trade_app"   (the project folder)
PROJECT_DIR = Path(__file__).resolve().parent.parent
DB_FILE = PROJECT_DIR / "trades.db"

# SQLAlchemy connection string. "sqlite:///" + absolute path to the file.
# The file is created automatically the first time we connect.
SQLALCHEMY_DATABASE_URL = f"sqlite:///{DB_FILE}"

# ---------------------------------------------------------------------------
# 2. The engine: the low-level object that talks to the database
# ---------------------------------------------------------------------------
# check_same_thread=False is required for SQLite + FastAPI, because FastAPI may
# handle a request on a different thread than the one that created the session.
engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
)

# ---------------------------------------------------------------------------
# 3. SessionLocal: a factory that creates database "sessions"
# ---------------------------------------------------------------------------
# A session is one short conversation with the database (read some rows,
# write some rows, commit). We create a fresh one for every HTTP request.
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

# ---------------------------------------------------------------------------
# 4. Base: the parent class for all our ORM models (see models.py)
# ---------------------------------------------------------------------------
Base = declarative_base()


# ---------------------------------------------------------------------------
# 5. get_db: a FastAPI "dependency"
# ---------------------------------------------------------------------------
def get_db():
    """
    Open a database session, hand it to the endpoint function, and make sure
    it is always closed afterwards - even if the endpoint raises an error.

    Used in endpoints like:  def my_endpoint(db: Session = Depends(get_db)):
    """
    db = SessionLocal()
    try:
        yield db          # the endpoint runs here, using `db`
    finally:
        db.close()        # always runs, even on errors
