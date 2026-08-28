-- ==========================================================================
-- Cash Flow Oracle - schema (Track 04 scaffold)
-- Works on PostgreSQL; the SQLite fallback in db.py applies a trimmed version.
-- ==========================================================================

CREATE TABLE IF NOT EXISTS merchants (
    merchant_id   TEXT PRIMARY KEY,
    archetype     TEXT NOT NULL,
    display_name  TEXT NOT NULL,
    onboarded_on  DATE NOT NULL
);

CREATE TABLE IF NOT EXISTS merchant_settlements (
    merchant_id      TEXT NOT NULL REFERENCES merchants(merchant_id),
    settlement_date  DATE NOT NULL,
    gross_inr        NUMERIC(16,2) NOT NULL,   -- captured payment volume
    refunds_inr      NUMERIC(16,2) NOT NULL DEFAULT 0,
    fees_inr         NUMERIC(16,2) NOT NULL DEFAULT 0,
    net_settled_inr  NUMERIC(16,2) NOT NULL,   -- what actually hits the bank
    txn_count        INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (merchant_id, settlement_date)
);
CREATE INDEX IF NOT EXISTS ix_settle_date ON merchant_settlements (settlement_date);

CREATE TABLE IF NOT EXISTS rbi_digital_payments (
    month                  TEXT PRIMARY KEY,   -- YYYY-MM
    upi_txn_millions       NUMERIC,
    card_txn_millions      NUMERIC,
    wallet_txn_millions    NUMERIC,
    digital_demand_index   NUMERIC
);

-- cached forecast runs (audit / debugging; not required by the API)
CREATE TABLE IF NOT EXISTS forecast_runs (
    id             BIGSERIAL PRIMARY KEY,
    merchant_id    TEXT NOT NULL,
    run_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    horizon_days   INTEGER NOT NULL,
    engine         TEXT NOT NULL,             -- prophet+garch+hmm | fallback
    current_cash_position NUMERIC,
    stress_days    INTEGER,
    recommendation TEXT
);
