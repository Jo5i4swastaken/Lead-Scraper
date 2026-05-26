"""Hosted-mode WebSocket server for the lead-scraper agent.

Step 3 deliverable. In ``hosted`` mode the agent process runs as a
shared multi-tenant service: each connecting CRM admin authenticates
on the WebSocket handshake with their Supabase JWT, and the agent
calls back into the CRM as *that* user (not as a single baked-in
service account).

See :mod:`rgv_lead_scraper.server.app` for the FastAPI bootstrap and
:mod:`rgv_lead_scraper.server.connection_context` for per-request
JWT isolation.
"""
