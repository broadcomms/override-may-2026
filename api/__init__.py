"""api — FastAPI HTTP runtime wrapping core.pipeline.

Endpoint contracts in `docs/04-api.md`. Tier-1 (P2.7 follow-up):
  GET  /api/health
  GET  /api/version
  POST /api/sessions
  GET  /api/sessions/{id}
  GET  /api/sessions/{id}/zones/{zone_id}?mode=engineer|fan|both
  GET  /api/regulation-source
"""
