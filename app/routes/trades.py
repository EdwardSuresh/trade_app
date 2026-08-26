"""
routes/trades.py
----------------
All of the API endpoints live here, grouped on an APIRouter.

An APIRouter works just like the FastAPI app object - you decorate functions
with @router.get(...), @router.post(...) and so on - but it is not a whole
application by itself. app/main.py imports this router and plugs it in with
app.include_router(router). Keeping the routes here keeps main.py short.
"""

from collections import defaultdict
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app import models, schema
from app.database import get_db

# Every path below is written in full (e.g. "/api/accounts"), so there is no
# prefix to remember. The router is included by app/main.py.
router = APIRouter()


# ===========================================================================
# Small helper functions (used by several endpoints)
# ===========================================================================
def get_account_or_404(db: Session, account_id: int) -> models.Account:
    """Fetch one account, or raise a clean 404 error if it does not exist."""
    account = db.query(models.Account).filter(models.Account.id == account_id).first()
    if account is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Account {account_id} not found",
        )
    return account


def net_shares_held(db: Session, account_id: int, symbol: str) -> int:
    """
    How many shares of `symbol` does this account own right now?

    = (all EXECUTED BUY quantities) - (all EXECUTED SELL quantities)
    Cancelled trades are ignored, as if they never happened.
    """
    trades = (
        db.query(models.Trade)
        .filter(
            models.Trade.account_id == account_id,
            models.Trade.symbol == symbol,
            models.Trade.status == "EXECUTED",
        )
        .all()
    )
    net = 0
    for t in trades:
        net += t.quantity if t.side == "BUY" else -t.quantity
    return net


# ===========================================================================
# ACCOUNT ENDPOINTS
# ===========================================================================
@router.post(
    "/api/accounts",
    response_model=schema.AccountResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["Accounts"],
)
def create_account(payload: schema.AccountCreate, db: Session = Depends(get_db)):
    """Create a new account. It starts with $100,000 of virtual cash."""
    # E-mails must be unique -> check first so we can return a friendly error.
    existing = (
        db.query(models.Account)
        .filter(models.Account.email == payload.email)
        .first()
    )
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="An account with e-mail '" + payload.email + "' already exists",
        )

    account = models.Account(
        owner_name=payload.owner_name,
        email=payload.email,
        cash_balance=models.STARTING_CASH,
    )
    db.add(account)      # stage the new row
    db.commit()          # actually write it to the database
    db.refresh(account)  # reload it so we get the generated id / created_at
    return account


@router.get(
    "/api/accounts",
    response_model=List[schema.AccountResponse],
    tags=["Accounts"],
)
def list_accounts(db: Session = Depends(get_db)):
    """List every account (each one includes its trades)."""
    return db.query(models.Account).order_by(models.Account.id).all()


@router.get(
    "/api/accounts/{account_id}",
    response_model=schema.AccountResponse,
    tags=["Accounts"],
)
def get_account(account_id: int, db: Session = Depends(get_db)):
    """Get one account together with all of its trades."""
    return get_account_or_404(db, account_id)


@router.delete(
    "/api/accounts/{account_id}",
    status_code=status.HTTP_200_OK,
    tags=["Accounts"],
)
def delete_account(account_id: int, db: Session = Depends(get_db)):
    """Delete an account. Its trades are deleted too (cascade)."""
    account = get_account_or_404(db, account_id)
    db.delete(account)
    db.commit()
    return {"message": f"Account {account_id} and all of its trades were deleted"}


# ===========================================================================
# TRADE ENDPOINTS
# ===========================================================================
@router.post(
    "/api/trades",
    response_model=schema.TradeResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["Trades"],
)
def place_trade(payload: schema.TradeCreate, db: Session = Depends(get_db)):
    """
    Place a BUY or SELL trade.

    Business rules:
      * the account must exist                         -> 404
      * quantity and price must be positive            -> 400
      * side must be BUY or SELL                       -> 400
      * BUY  : cost must not exceed the account's cash -> 400 Insufficient funds
      * SELL : the account must own enough shares      -> 400 Insufficient shares
    """
    account = get_account_or_404(db, payload.account_id)

    # All the business rules are checked here, in one place, so every broken
    # rule produces a clear 400 error message.
    if payload.quantity <= 0:
        raise HTTPException(status_code=400, detail="Quantity must be greater than 0")
    if payload.price <= 0:
        raise HTTPException(status_code=400, detail="Price must be greater than 0")

    side = payload.side.upper()
    if side not in ("BUY", "SELL"):
        raise HTTPException(status_code=400, detail="Side must be either BUY or SELL")

    symbol = payload.symbol.strip().upper()   # always store symbols uppercase
    trade_value = round(payload.quantity * payload.price, 2)

    # --- money / share checks ------------------------------------------------
    if side == "BUY":
        if trade_value > account.cash_balance:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Insufficient funds: trade costs ${trade_value:,.2f} "
                    f"but cash balance is ${account.cash_balance:,.2f}"
                ),
            )
        account.cash_balance = round(account.cash_balance - trade_value, 2)
    else:  # SELL
        held = net_shares_held(db, account.id, symbol)
        if payload.quantity > held:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Insufficient shares: trying to sell {payload.quantity} "
                    f"{symbol} but only {held} held"
                ),
            )
        account.cash_balance = round(account.cash_balance + trade_value, 2)

    # --- save the trade ------------------------------------------------------
    trade = models.Trade(
        account_id=account.id,
        symbol=symbol,
        side=side,
        quantity=payload.quantity,
        price=payload.price,
        status="EXECUTED",
    )
    db.add(trade)
    db.commit()
    db.refresh(trade)
    return trade


@router.get(
    "/api/trades",
    response_model=List[schema.TradeResponse],
    tags=["Trades"],
)
def list_trades(
    account_id: Optional[int] = Query(None, description="Only trades of this account"),
    symbol: Optional[str] = Query(None, description="Only trades of this symbol"),
    side: Optional[str] = Query(None, description="BUY or SELL"),
    db: Session = Depends(get_db),
):
    """List trades, newest first. All three query filters are optional."""
    query = db.query(models.Trade)

    if account_id is not None:
        query = query.filter(models.Trade.account_id == account_id)
    if symbol:
        query = query.filter(models.Trade.symbol == symbol.strip().upper())
    if side:
        query = query.filter(models.Trade.side == side.strip().upper())

    return query.order_by(models.Trade.id.desc()).all()


@router.put(
    "/api/trades/{trade_id}/cancel",
    response_model=schema.TradeResponse,
    tags=["Trades"],
)
def cancel_trade(trade_id: int, db: Session = Depends(get_db)):
    """
    Cancel a trade and undo its effect on cash:
      * cancelling a BUY  -> the money spent comes back
      * cancelling a SELL -> the proceeds are taken back out
    """
    trade = db.query(models.Trade).filter(models.Trade.id == trade_id).first()
    if trade is None:
        raise HTTPException(status_code=404, detail=f"Trade {trade_id} not found")

    if trade.status == "CANCELLED":
        raise HTTPException(status_code=400, detail="Trade is already cancelled")

    account = get_account_or_404(db, trade.account_id)
    trade_value = round(trade.quantity * trade.price, 2)

    if trade.side == "BUY":
        account.cash_balance = round(account.cash_balance + trade_value, 2)
    else:
        account.cash_balance = round(account.cash_balance - trade_value, 2)

    trade.status = "CANCELLED"
    db.commit()
    db.refresh(trade)
    return trade


# ===========================================================================
# PORTFOLIO ENDPOINT
# ===========================================================================
@router.get(
    "/api/accounts/{account_id}/portfolio",
    response_model=schema.PortfolioResponse,
    tags=["Portfolio"],
)
def get_portfolio(account_id: int, db: Session = Depends(get_db)):
    """
    Build the portfolio for one account from its EXECUTED trades.

    For every symbol we work out:
      net_quantity      = shares bought - shares sold
      average_buy_price = total spent on BUYs / total shares bought
      invested_amount   = net_quantity x average_buy_price
    """
    account = get_account_or_404(db, account_id)

    executed = (
        db.query(models.Trade)
        .filter(
            models.Trade.account_id == account_id,
            models.Trade.status == "EXECUTED",
        )
        .order_by(models.Trade.id)
        .all()
    )

    # Running totals per symbol. defaultdict saves us from writing
    # "if symbol not in dict: dict[symbol] = 0" everywhere.
    bought_qty: Dict[str, int] = defaultdict(int)
    bought_cost: Dict[str, float] = defaultdict(float)
    sold_qty: Dict[str, int] = defaultdict(int)

    for t in executed:
        if t.side == "BUY":
            bought_qty[t.symbol] += t.quantity
            bought_cost[t.symbol] += t.quantity * t.price
        else:
            sold_qty[t.symbol] += t.quantity

    holdings: List[schema.Holding] = []
    total_invested = 0.0

    for sym in sorted(set(bought_qty) | set(sold_qty)):
        net_qty = bought_qty[sym] - sold_qty[sym]
        if net_qty <= 0:
            continue  # position fully closed - nothing left to show

        avg_price = bought_cost[sym] / bought_qty[sym] if bought_qty[sym] else 0.0
        invested = round(net_qty * avg_price, 2)
        total_invested += invested

        holdings.append(
            schema.Holding(
                symbol=sym,
                net_quantity=net_qty,
                average_buy_price=round(avg_price, 2),
                invested_amount=invested,
            )
        )

    total_invested = round(total_invested, 2)
    return schema.PortfolioResponse(
        account_id=account.id,
        owner_name=account.owner_name,
        cash_balance=round(account.cash_balance, 2),
        holdings=holdings,
        total_invested=total_invested,
        total_value=round(account.cash_balance + total_invested, 2),
    )
