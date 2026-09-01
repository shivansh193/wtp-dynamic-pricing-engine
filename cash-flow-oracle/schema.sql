-- ==========================================================================
-- Cash Flow Oracle - schema (Track 04 scaffold)
-- Works on PostgreSQL; the SQLite fallback in db.py applies a trimmed version.
-- ==========================================================================

CREATE TABLE IF NOT EXISTS merchants (
    merchant_id                TEXT PRIMARY KEY,
    archetype                  TEXT NOT NULL,       -- == merchant_category
    display_name               TEXT NOT NULL,
    onboarded_on               DATE NOT NULL,
    city_tier                  INTEGER,
    avg_daily_settlement       NUMERIC(16,2),       -- trailing-365d mean, INR
    settlement_volatility      NUMERIC(10,6),       -- GARCH-derived daily return vol
    operating_threshold        NUMERIC(16,2),       -- 30% of monthly avg settlement
    capital_disbursement_days  INTEGER,             -- Razorpay Capital lead time (2-3)
    late_payment_penalty_rate  NUMERIC(6,3)         -- % per month (1.5-3.0)
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

-- scenario simulator runs, keyed by merchant + scenario id
CREATE TABLE IF NOT EXISTS scenario_runs (
    scenario_id      TEXT PRIMARY KEY,
    merchant_id      TEXT NOT NULL,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    shock_type       TEXT NOT NULL,
    shock_magnitude  NUMERIC NOT NULL,        -- percentage, e.g. 20 = +/-20%
    shock_start_date DATE NOT NULL,
    shock_duration_days INTEGER NOT NULL,
    result           JSONB NOT NULL           -- full scenario response snapshot
);
CREATE INDEX IF NOT EXISTS ix_scenario_merchant ON scenario_runs (merchant_id);

-- 6-hour cache for the LLM (Claude) recommendation
CREATE TABLE IF NOT EXISTS llm_recommendations (
    merchant_id   TEXT NOT NULL,
    context_hash  TEXT NOT NULL,              -- hash of the prompt inputs
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    recommendation TEXT NOT NULL,
    model         TEXT NOT NULL,
    source        TEXT NOT NULL,              -- "llm" | "template"
    PRIMARY KEY (merchant_id, context_hash)
);
