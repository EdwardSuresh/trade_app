"""
schema.py
---------
Pydantic models ("schemas") describe the JSON that goes IN to the API and the
JSON that comes OUT of it.

Rule of thumb:
  *Create  schemas  -> what the client must send us
  *Response schemas -> what we send back

`model_config = ConfigDict(from_attributes=True)` lets Pydantic read data
straight off a SQLAlchemy object (account.owner_name) instead of a dict.
"""

from datetime import datetime
from typing import List

from pydantic import BaseModel, ConfigDict, Field, computed_field

# We keep e-mail as a plain string so no extra packages are needed.
# Uniqueness is enforced by the database (see models.Account.email).


# ===========================================================================
# Accounts
# ===========================================================================
class AccountCreate(BaseModel):
    """Body for POST /api/accounts."""

    owner_name: str = Field(..., min_length=1, examples=["Ada Lovelace"])
    email: str = Field(..., min_length=3, examples=["ada@example.com"])


# ===========================================================================
# Trades
# ===========================================================================
class TradeCreate(BaseModel):
    """Body for POST /api/trades."""

    account_id: int = Field(..., examples=[1])
    symbol: str = Field(..., min_length=1, examples=["AAPL"])
    side: str = Field(..., examples=["BUY"])       # must be "BUY" or "SELL"
    quantity: int = Field(..., examples=[10])      # must be > 0
    price: float = Field(..., examples=[150.25])   # price per share, must be > 0

    # NOTE: the "must be positive" and "must be BUY/SELL" rules are checked
    # inside the endpoint (app/main.py) instead of here, so that breaking them
    # returns a friendly 400 error rather than Pydantic's generic 422.


class TradeResponse(BaseModel):
    """One trade as returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    account_id: int
    symbol: str
    side: str
    quantity: int
    price: float
    status: str
    created_at: datetime

    @computed_field  # type: ignore[prop-decorator]
    @property
    def total_value(self) -> float:
        """Money moved by this trade = quantity x price."""
        return round(self.quantity * self.price, 2)


class AccountResponse(BaseModel):
    """One account, including all of its trades."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    owner_name: str
    email: str
    cash_balance: float
    created_at: datetime
    trades: List[TradeResponse] = []


# ===========================================================================
# Portfolio
# ===========================================================================
class Holding(BaseModel):
    """How much of ONE symbol an account currently owns."""

    symbol: str
    net_quantity: int          # shares bought minus shares sold
    average_buy_price: float   # average price paid per share on BUYs
    invested_amount: float     # net_quantity x average_buy_price


class PortfolioResponse(BaseModel):
    """Everything the portfolio screen needs for one account."""

    account_id: int
    owner_name: str
    cash_balance: float
    holdings: List[Holding] = []
    total_invested: float      # sum of invested_amount over all holdings
    total_value: float         # cash_balance + total_invested (the grand total)
