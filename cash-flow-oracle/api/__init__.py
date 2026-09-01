"""Cash Flow Oracle - HTTP surface (Track 04).

`oracle_routes.router` carries every `/oracle/*` endpoint and is mounted on
both the standalone CFO app (`cash_flow_oracle.main`) and the Track 01 API so
the deployed service exposes the oracle alongside the pricing engine.
"""
