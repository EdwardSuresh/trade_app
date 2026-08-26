"""
models.py
---------
The database tables, described as Python classes (SQLAlchemy ORM models).

Two tables:
  Account  - a trading account holding virtual cash
  Trade    - one buy or sell order belonging to an account

The relationship is "one-to-many": one Account has many Trades.
"""

from datetime import datetime

from sqlalchemy import (
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
)
from sqlalchemy.orm import relationship

from app.database import Base

# Every new account starts with this much virtual cash.
STARTING_CASH = 100000.0


class Account(Base):
    """A trading account. Owns cash and a list of trades."""

    __tablename__ = "accounts"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    owner_name = Column(String, nullable=False)
    # unique=True means two accounts can never share an email address.
    email = Column(String, unique=True, nullable=False, index=True)
    cash_balance = Column(Float, nullable=False, default=STARTING_CASH)
    created_at = Column(DateTime, default=datetime.now, nullable=False)

    # account.trades -> list of Trade objects.
    # cascade="all, delete-orphan" means: deleting an account also deletes its
    # trades, so we never leave orphan rows behind.
    trades = relationship(
        "Trade",
        back_populates="account",
        cascade="all, delete-orphan",
        order_by="Trade.id",
    )

    def __repr__(self) -> str:  # handy when printing/debugging
        return f"<Account id={self.id} {self.owner_name} cash={self.cash_balance}>"


class Trade(Base):
    """One executed (or cancelled) buy/sell order."""

    __tablename__ = "trades"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    # ForeignKey ties this row to a row in the accounts table.
    account_id = Column(
        Integer,
        ForeignKey("accounts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # Ticker symbol, always stored uppercase (we uppercase it in main.py).
    symbol = Column(String, nullable=False, index=True)
    # "BUY" or "SELL"
    side = Column(String, nullable=False)
    quantity = Column(Integer, nullable=False)      # must be > 0 (checked in main.py)
    price = Column(Float, nullable=False)           # price per share, must be > 0
    # "EXECUTED" or "CANCELLED"
    status = Column(String, nullable=False, default="EXECUTED")
    created_at = Column(DateTime, default=datetime.now, nullable=False)

    # trade.account -> the Account object this trade belongs to.
    account = relationship("Account", back_populates="trades")

    def __repr__(self) -> str:
        return f"<Trade id={self.id} {self.side} {self.quantity} {self.symbol} @ {self.price}>"
