-- ==========================================================================
-- WTP Dynamic Pricing Engine - PostgreSQL schema
-- Applied automatically by docker-compose (mounted into /docker-entrypoint-
-- initdb.d) and by api.db.init_db() on startup if the tables are missing.
-- ==========================================================================

CREATE TABLE IF NOT EXISTS pricing_decisions (
    id                       BIGSERIAL PRIMARY KEY,
    session_id               TEXT        NOT NULL,
    created_at               TIMESTAMPTZ NOT NULL DEFAULT now(),

    -- request
    input_signals            JSONB       NOT NULL,
    ip_address               INET,
    list_price               NUMERIC(12,2) NOT NULL,

    -- ip enrichment
    ip_type                  TEXT,
    ip_trust_multiplier      NUMERIC(6,4),
    ip_is_whitelisted        BOOLEAN,

    -- model
    wtp_score                NUMERIC(8,5) NOT NULL,
    conversion_probability   NUMERIC(8,5),
    model_confidence         TEXT,
    shap_values              JSONB,

    -- decision
    final_price              NUMERIC(12,2) NOT NULL,
    price_delta_pct          NUMERIC(7,3)  NOT NULL,
    offer_type               TEXT          NOT NULL,
    payment_methods_shown    JSONB         NOT NULL,
    cod_eligible             BOOLEAN,
    instant_refund_eligible  BOOLEAN,
    reasoning                TEXT,

    -- ops
    latency_ms               NUMERIC(8,3)  NOT NULL,
    budget_exceeded          BOOLEAN       NOT NULL DEFAULT false
);

CREATE INDEX IF NOT EXISTS ix_pricing_decisions_session   ON pricing_decisions (session_id);
CREATE INDEX IF NOT EXISTS ix_pricing_decisions_created   ON pricing_decisions (created_at DESC);
CREATE INDEX IF NOT EXISTS ix_pricing_decisions_offer     ON pricing_decisions (offer_type);
CREATE INDEX IF NOT EXISTS ix_pricing_decisions_ip_type   ON pricing_decisions (ip_type);

-- Convenience view for the /metrics endpoint: one row per decision with the
-- segment key pre-computed.
CREATE OR REPLACE VIEW v_decision_segments AS
SELECT
    d.*,
    (d.input_signals ->> 'city_tier')                 AS city_tier,
    (d.input_signals ->> 'device_type')               AS device_type,
    (d.input_signals ->> 'payment_method_preference') AS payment_pref,
    concat_ws('|',
        d.input_signals ->> 'city_tier',
        d.input_signals ->> 'device_type',
        d.input_signals ->> 'payment_method_preference'
    ) AS segment_key
FROM pricing_decisions d;

-- ==========================================================================
-- Demo sessions (link-generator flow): one row per generated customer link.
--   pending  -> link created, customer hasn't priced yet
--   priced   -> customer hit "See my price" (POST /personalize)
--   converted-> customer clicked "Complete Purchase" (dummy)
--   abandoned-> explicitly abandoned / timed out
-- ==========================================================================
CREATE TABLE IF NOT EXISTS sessions (
    session_id     TEXT PRIMARY KEY,
    merchant_id    TEXT        NOT NULL,
    preset         TEXT        NOT NULL,          -- random | high | mid | low | custom
    config         JSONB       NOT NULL,          -- pre-populated customer signals
    status         TEXT        NOT NULL DEFAULT 'pending',
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    priced_at      TIMESTAMPTZ,
    completed_at   TIMESTAMPTZ,
    list_price     NUMERIC(12,2),
    price_shown    NUMERIC(12,2),
    wtp_score      NUMERIC(8,5),
    offer_type     TEXT,
    segment_key    TEXT,
    result         JSONB                          -- full PricingResponse snapshot
);
CREATE INDEX IF NOT EXISTS ix_sessions_created ON sessions (created_at DESC);
CREATE INDEX IF NOT EXISTS ix_sessions_status  ON sessions (status);
CREATE INDEX IF NOT EXISTS ix_sessions_segment ON sessions (segment_key);
