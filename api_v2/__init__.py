"""api_v2 — FastAPI JSON backend for vite_dashboard.

Reuses hf_dashboard/services, hf_dashboard/engines, hf_dashboard/loader.
Per STANDARDS §11, the actual rename of hf_dashboard/ → dashboard/ happens
in Phase 5 after v1 decommission. Until then, both Spaces import from
hf_dashboard/services.
"""
