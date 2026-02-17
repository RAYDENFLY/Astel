-- SQLite schema for quant_system

PRAGMA journal_mode=WAL;

CREATE TABLE IF NOT EXISTS trades (
    trade_id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    asset TEXT NOT NULL,
    side TEXT NOT NULL,
    qty REAL NOT NULL,
    entry_order_id TEXT,
    tp_order_id TEXT,
    sl_order_id TEXT,
    entry_price REAL NOT NULL,
    entry_fee REAL,
    stop_price REAL NOT NULL,
    tp_price REAL,
    stop_distance REAL NOT NULL,
    leverage_implied REAL NOT NULL,
    prediction REAL NOT NULL,
    risk_at_stop REAL NOT NULL,
    status TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS trade_closures (
    closure_id INTEGER PRIMARY KEY AUTOINCREMENT,
    trade_id INTEGER,
    timestamp TEXT NOT NULL,
    asset TEXT NOT NULL,
    side TEXT NOT NULL,
    qty REAL NOT NULL,
    exit_order_id TEXT,
    entry_price REAL NOT NULL,
    exit_price REAL NOT NULL,
    exit_reason TEXT NOT NULL,
    gross_pnl REAL NOT NULL,
    fees REAL NOT NULL,
    pnl REAL NOT NULL,
    FOREIGN KEY(trade_id) REFERENCES trades(trade_id)
);

CREATE TABLE IF NOT EXISTS equity_curve (
    ts TEXT PRIMARY KEY,
    equity REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS weekly_performance (
    week_id TEXT PRIMARY KEY,
    start_ts TEXT NOT NULL,
    end_ts TEXT NOT NULL,
    trades INTEGER NOT NULL,
    win_rate REAL NOT NULL,
    avg_win REAL NOT NULL,
    avg_loss REAL NOT NULL,
    profit_factor REAL NOT NULL,
    total_pnl REAL NOT NULL,
    return_pct REAL NOT NULL,
    max_drawdown REAL NOT NULL,
    sharpe REAL NOT NULL
);

-- Generic key/value runner state (e.g., peak_equity for live runner)
CREATE TABLE IF NOT EXISTS runner_state (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_ts TEXT NOT NULL
);
