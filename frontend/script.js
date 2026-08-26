/* =========================================================================
   script.js - all the browser-side logic for Trade Station.

   How it works, in one sentence:
   the page never reloads; instead we call the FastAPI backend with fetch()
   and re-draw the parts of the page that changed.
   ========================================================================= */

// The id of the account currently selected in the dropdown (null = none yet).
let activeAccountId = null;

// Shortcut so we do not type document.getElementById everywhere.
const $ = (id) => document.getElementById(id);


/* =========================================================================
   1. One small helper for every API call
   ========================================================================= */

/**
 * Call the backend and return the parsed JSON.
 *
 * @param {string} path   e.g. "/api/accounts"
 * @param {string} method "GET" (default), "POST", "PUT", "DELETE"
 * @param {object} body   optional JavaScript object, sent as JSON
 * @throws {Error} with the API's own message when the response is not 2xx
 */
async function api(path, method = "GET", body = null) {
  const options = { method, headers: { "Content-Type": "application/json" } };
  if (body !== null) {
    options.body = JSON.stringify(body);
  }

  const response = await fetch(path, options);

  // Try to read the JSON body; some responses (rare) may not have one.
  let data = null;
  try {
    data = await response.json();
  } catch (e) {
    data = null;
  }

  if (!response.ok) {
    // FastAPI puts error text in "detail". It can be a string or a list
    // (Pydantic validation errors), so handle both.
    let message = "Request failed (" + response.status + ")";
    if (data && data.detail) {
      message = typeof data.detail === "string"
        ? data.detail
        : data.detail.map((d) => d.msg).join(", ");
    }
    throw new Error(message);
  }

  return data;
}


/* =========================================================================
   2. Tiny display helpers
   ========================================================================= */

/** Format a number as US dollars, e.g. 1234.5 -> "$1,234.50" */
function money(value) {
  return "$" + Number(value).toLocaleString("en-US", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
}

/** Format an ISO timestamp as a short local date + time. */
function timestamp(isoString) {
  const d = new Date(isoString);
  return d.toLocaleString();
}

/** Show a green (success) or red (error) message at the top of the page. */
function showBanner(message, type) {
  const banner = $("banner");
  banner.textContent = message;
  banner.className = "banner banner-" + type;  // banner-success / banner-error
  // Hide it again after a few seconds so the page stays tidy.
  clearTimeout(showBanner.timer);
  showBanner.timer = setTimeout(() => banner.classList.add("hidden"), 6000);
}


/* =========================================================================
   3. Loading data from the API
   ========================================================================= */

/** Fill the account dropdown from GET /api/accounts. */
async function loadAccounts() {
  const accounts = await api("/api/accounts");
  const select = $("account-select");
  select.innerHTML = "";

  if (accounts.length === 0) {
    select.innerHTML = '<option value="">No accounts yet - create one</option>';
    activeAccountId = null;
    return;
  }

  // Build one <option> per account.
  for (const account of accounts) {
    const option = document.createElement("option");
    option.value = account.id;
    option.textContent = account.owner_name + " (" + account.email + ")";
    select.appendChild(option);
  }

  // Keep the current selection if it still exists, otherwise pick the first.
  const stillExists = accounts.some((a) => a.id === activeAccountId);
  activeAccountId = stillExists ? activeAccountId : accounts[0].id;
  select.value = activeAccountId;
}

/** Refresh the three summary cards + the portfolio table. */
async function loadPortfolio() {
  const portfolioBody = $("portfolio-body");

  if (!activeAccountId) {
    $("card-cash").textContent = money(0);
    $("card-invested").textContent = money(0);
    portfolioBody.innerHTML =
      '<tr><td colspan="4" class="empty">Create an account to get started.</td></tr>';
    return;
  }

  const portfolio = await api("/api/accounts/" + activeAccountId + "/portfolio");

  $("card-cash").textContent = money(portfolio.cash_balance);
  $("card-invested").textContent = money(portfolio.total_invested);

  if (portfolio.holdings.length === 0) {
    portfolioBody.innerHTML =
      '<tr><td colspan="4" class="empty">No holdings yet.</td></tr>';
    return;
  }

  portfolioBody.innerHTML = "";
  for (const h of portfolio.holdings) {
    const row = document.createElement("tr");
    row.innerHTML =
      "<td><strong>" + h.symbol + "</strong></td>" +
      '<td class="num">' + h.net_quantity + "</td>" +
      '<td class="num">' + money(h.average_buy_price) + "</td>" +
      '<td class="num">' + money(h.invested_amount) + "</td>";
    portfolioBody.appendChild(row);
  }
}

/** Refresh the trade history table (newest first) and the trade count card. */
async function loadHistory() {
  const historyBody = $("history-body");

  if (!activeAccountId) {
    $("card-trades").textContent = "0";
    historyBody.innerHTML =
      '<tr><td colspan="8" class="empty">No trades yet.</td></tr>';
    return;
  }

  // The API already returns newest first.
  const trades = await api("/api/trades?account_id=" + activeAccountId);
  $("card-trades").textContent = trades.length;

  if (trades.length === 0) {
    historyBody.innerHTML =
      '<tr><td colspan="8" class="empty">No trades yet.</td></tr>';
    return;
  }

  historyBody.innerHTML = "";
  for (const t of trades) {
    const sideClass = t.side === "BUY" ? "side-buy" : "side-sell";
    const tagClass = t.status === "EXECUTED" ? "tag-executed" : "tag-cancelled";

    const row = document.createElement("tr");
    row.innerHTML =
      "<td><strong>" + t.symbol + "</strong></td>" +
      '<td class="' + sideClass + '">' + t.side + "</td>" +
      '<td class="num">' + t.quantity + "</td>" +
      '<td class="num">' + money(t.price) + "</td>" +
      '<td class="num">' + money(t.total_value) + "</td>" +
      '<td><span class="tag ' + tagClass + '">' + t.status + "</span></td>" +
      "<td>" + timestamp(t.created_at) + "</td>" +
      "<td></td>";

    // Only executed trades can be cancelled, so only they get a button.
    if (t.status === "EXECUTED") {
      const button = document.createElement("button");
      button.className = "btn btn-small";
      button.textContent = "Cancel";
      button.addEventListener("click", () => cancelTrade(t.id));
      row.lastElementChild.appendChild(button);
    }

    historyBody.appendChild(row);
  }
}

/** Re-draw everything that depends on the selected account. */
async function refreshAll() {
  try {
    await loadPortfolio();
    await loadHistory();
  } catch (error) {
    showBanner(error.message, "error");
  }
}


/* =========================================================================
   4. Actions (things the user clicks)
   ========================================================================= */

/** Create a new account from the header form. */
async function createAccount(event) {
  event.preventDefault();               // do not reload the page
  const ownerName = $("new-owner-name").value.trim();
  const email = $("new-email").value.trim();

  try {
    const account = await api("/api/accounts", "POST", {
      owner_name: ownerName,
      email: email,
    });

    activeAccountId = account.id;       // select the brand new account
    $("new-account-form").reset();
    showBanner("Account created for " + account.owner_name, "success");

    await loadAccounts();
    await refreshAll();
  } catch (error) {
    showBanner(error.message, "error");
  }
}

/** Place a BUY or SELL trade from the trade form. */
async function placeTrade(event) {
  event.preventDefault();

  if (!activeAccountId) {
    showBanner("Create or select an account first", "error");
    return;
  }

  const payload = {
    account_id: Number(activeAccountId),
    symbol: $("trade-symbol").value.trim().toUpperCase(),
    side: $("trade-side").value,
    quantity: Number($("trade-quantity").value),
    price: Number($("trade-price").value),
  };

  try {
    const trade = await api("/api/trades", "POST", payload);
    showBanner(
      trade.side + " " + trade.quantity + " " + trade.symbol +
      " for " + money(trade.total_value) + " executed",
      "success"
    );
    $("trade-form").reset();
    await refreshAll();
  } catch (error) {
    // e.g. "Insufficient funds: ..." or "Insufficient shares: ..."
    showBanner(error.message, "error");
  }
}

/** Cancel one trade and put the money back. */
async function cancelTrade(tradeId) {
  try {
    await api("/api/trades/" + tradeId + "/cancel", "PUT");
    showBanner("Trade #" + tradeId + " cancelled", "success");
    await refreshAll();
  } catch (error) {
    showBanner(error.message, "error");
  }
}


/* =========================================================================
   5. Wire everything up when the page loads
   ========================================================================= */
document.addEventListener("DOMContentLoaded", async () => {
  $("new-account-form").addEventListener("submit", createAccount);
  $("trade-form").addEventListener("submit", placeTrade);

  // Switching account in the dropdown reloads the cards, portfolio and history.
  $("account-select").addEventListener("change", async (event) => {
    activeAccountId = event.target.value ? Number(event.target.value) : null;
    await refreshAll();
  });

  try {
    await loadAccounts();
    await refreshAll();
  } catch (error) {
    showBanner("Could not reach the API: " + error.message, "error");
  }
});
