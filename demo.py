"""
demo.py
-------
A guided tour of the Trade Station API.

It uses ONLY the Python standard library (urllib + json), so there is nothing
extra to install.

BEFORE RUNNING: start the server in another terminal:
    uvicorn app.main:app --reload

Then run:
    python demo.py
"""

import json
import urllib.error
import urllib.request

BASE_URL = "http://127.0.0.1:8000"


# ===========================================================================
# A tiny HTTP helper
# ===========================================================================
def call_api(path, method="GET", body=None):
    """
    Send one request to the API.

    Returns a tuple: (status_code, parsed_json)
    Errors (400/404/...) are returned instead of raised, so the demo can
    print the API's error messages nicely.
    """
    url = BASE_URL + path
    data = json.dumps(body).encode("utf-8") if body is not None else None

    request = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={"Content-Type": "application/json"},
    )

    try:
        with urllib.request.urlopen(request) as response:
            payload = response.read().decode("utf-8")
            return response.status, (json.loads(payload) if payload else None)
    except urllib.error.HTTPError as error:
        # The server answered, but with an error status (400, 404, 422...).
        payload = error.read().decode("utf-8")
        try:
            return error.code, json.loads(payload)
        except json.JSONDecodeError:
            return error.code, {"detail": payload}
    except urllib.error.URLError as error:
        print("\nERROR: could not reach the server at " + BASE_URL)
        print("Is it running?  ->  uvicorn app.main:app --reload")
        print("Details:", error.reason)
        raise SystemExit(1)


def error_message(response_body):
    """Pull the human-readable message out of a FastAPI error response."""
    detail = (response_body or {}).get("detail", response_body)
    if isinstance(detail, list):  # Pydantic validation errors come as a list
        return "; ".join(item.get("msg", str(item)) for item in detail)
    return str(detail)


def heading(text):
    """Print a clear step header so the output is easy to follow."""
    print()
    print("=" * 66)
    print(text)
    print("=" * 66)


def money(value):
    """1234.5 -> '$1,234.50'"""
    return "${:,.2f}".format(value)


# ===========================================================================
# Step 1 - create two accounts
# ===========================================================================
def create_accounts():
    heading("STEP 1  Create two trading accounts")
    accounts = []

    people = [
        {"owner_name": "Alice Trader", "email": "alice.demo@example.com"},
        {"owner_name": "Bob Investor", "email": "bob.demo@example.com"},
    ]

    for person in people:
        status, body = call_api("/api/accounts", "POST", person)

        if status == 201:
            print("Created account #{id}: {name} - cash {cash}".format(
                id=body["id"], name=body["owner_name"],
                cash=money(body["cash_balance"]),
            ))
            accounts.append(body)
        else:
            # Most likely the demo was run before and the e-mail already exists.
            print("Could not create {}: {}".format(
                person["email"], error_message(body)))
            print("  -> looking up the existing account instead...")
            _, everyone = call_api("/api/accounts")
            match = [a for a in everyone if a["email"] == person["email"]]
            if not match:
                raise SystemExit("Unexpected: account missing. Delete trades.db and retry.")
            print("  -> reusing account #{} ({})".format(
                match[0]["id"], match[0]["owner_name"]))
            accounts.append(match[0])

    return accounts


# ===========================================================================
# Step 2 - place six trades that all succeed
# ===========================================================================
def place_good_trades(alice_id, bob_id):
    heading("STEP 2  Place six valid trades (3 symbols, BUY and SELL)")

    trades = [
        # Alice buys three different symbols...
        {"account_id": alice_id, "symbol": "AAPL", "side": "BUY",  "quantity": 50, "price": 190.00},
        {"account_id": alice_id, "symbol": "MSFT", "side": "BUY",  "quantity": 20, "price": 410.50},
        # ...then sells part of her AAPL position (this SELL is legal because
        # she already owns 50 shares).
        {"account_id": alice_id, "symbol": "AAPL", "side": "SELL", "quantity": 20, "price": 205.00},
        # Bob buys two symbols and sells some of one of them.
        {"account_id": bob_id,   "symbol": "TSLA", "side": "BUY",  "quantity": 30, "price": 250.00},
        {"account_id": bob_id,   "symbol": "AAPL", "side": "BUY",  "quantity": 10, "price": 188.75},
        {"account_id": bob_id,   "symbol": "TSLA", "side": "SELL", "quantity": 10, "price": 262.40},
    ]

    for trade in trades:
        status, body = call_api("/api/trades", "POST", trade)
        if status == 201:
            print("OK   account {acct}: {side:<4} {qty:>4} {sym:<5} @ {price:>10}  total {total}".format(
                acct=body["account_id"], side=body["side"], qty=body["quantity"],
                sym=body["symbol"], price=money(body["price"]),
                total=money(body["total_value"]),
            ))
        else:
            print("FAIL {} {} -> {}".format(
                trade["side"], trade["symbol"], error_message(body)))


# ===========================================================================
# Step 3 - two trades that SHOULD fail (the business rules in action)
# ===========================================================================
def show_business_rules(alice_id, bob_id):
    heading("STEP 3  Two trades that must be rejected")

    print("\n3a) Alice tries to buy far more than her cash allows:")
    status, body = call_api("/api/trades", "POST", {
        "account_id": alice_id, "symbol": "NVDA", "side": "BUY",
        "quantity": 10000, "price": 900.00,
    })
    print("    HTTP {} -> {}".format(status, error_message(body)))

    print("\n3b) Bob tries to sell a stock he does not own:")
    status, body = call_api("/api/trades", "POST", {
        "account_id": bob_id, "symbol": "GOOG", "side": "SELL",
        "quantity": 5, "price": 175.00,
    })
    print("    HTTP {} -> {}".format(status, error_message(body)))


# ===========================================================================
# Step 4 - print each portfolio as a table
# ===========================================================================
def print_portfolio(account_id):
    status, portfolio = call_api("/api/accounts/{}/portfolio".format(account_id))
    if status != 200:
        print("Could not load portfolio: " + error_message(portfolio))
        return

    print("\nPortfolio of {} (account #{})".format(
        portfolio["owner_name"], portfolio["account_id"]))

    header = "{:<8} {:>13} {:>18} {:>18}".format(
        "SYMBOL", "NET QUANTITY", "AVG BUY PRICE", "INVESTED")
    print("-" * len(header))
    print(header)
    print("-" * len(header))

    if not portfolio["holdings"]:
        print("(no open positions)")
    else:
        for h in portfolio["holdings"]:
            print("{:<8} {:>13} {:>18} {:>18}".format(
                h["symbol"], h["net_quantity"],
                money(h["average_buy_price"]), money(h["invested_amount"]),
            ))

    print("-" * len(header))
    print("{:<8} {:>50}".format("Cash", money(portfolio["cash_balance"])))
    print("{:<8} {:>50}".format("Invested", money(portfolio["total_invested"])))
    print("{:<8} {:>50}".format("TOTAL", money(portfolio["total_value"])))


# ===========================================================================
# Main
# ===========================================================================
def main():
    print("Trade Station demo - talking to " + BASE_URL)

    accounts = create_accounts()
    alice_id = accounts[0]["id"]
    bob_id = accounts[1]["id"]

    place_good_trades(alice_id, bob_id)
    show_business_rules(alice_id, bob_id)

    heading("STEP 4  Final portfolios")
    print_portfolio(alice_id)
    print_portfolio(bob_id)

    heading("DONE  Open http://127.0.0.1:8000 to see the same data in the browser")


if __name__ == "__main__":
    main()
