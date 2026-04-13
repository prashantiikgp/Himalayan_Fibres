"""Himalayan Fibers Dashboard — FastAPI + Gradio.

Main entry point. FastAPI handles WhatsApp webhooks,
Gradio handles the dashboard UI. Both on port 7860.
Background thread checks pending flow steps every 30 minutes.
"""

from __future__ import annotations

import logging
import sys
import threading
import time
from pathlib import Path

# Ensure hf_dashboard is on the path
sys.path.insert(0, str(Path(__file__).resolve().parent))

# Load .env for local dev. On HF Spaces, env comes from Space Secrets —
# load_dotenv() is a no-op there because no .env file is shipped.
try:
    from dotenv import load_dotenv
    # Project root .env (one level up from hf_dashboard/)
    root_env = Path(__file__).resolve().parent.parent / ".env"
    if root_env.exists():
        load_dotenv(root_env)
    # Also try local-to-hf_dashboard .env for Docker-based dev
    local_env = Path(__file__).resolve().parent / ".env"
    if local_env.exists():
        load_dotenv(local_env, override=False)
except ImportError:
    pass  # python-dotenv not required in prod

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from engines.navigation_engine import build_app_with_sidebar
from services.database import ensure_db_ready
from services.config import get_settings

import gradio as gr

log = logging.getLogger(__name__)

# -- Initialize database on import --
ensure_db_ready()

# -- FastAPI app --
fastapi_app = FastAPI(title="Himalayan Fibers Dashboard")


@fastapi_app.get("/webhook/whatsapp")
async def wa_verify(request: Request):
    """Meta webhook verification handshake."""
    settings = get_settings()
    mode = request.query_params.get("hub.mode")
    token = request.query_params.get("hub.verify_token")
    challenge = request.query_params.get("hub.challenge")
    if mode == "subscribe" and token == settings.wa_verify_token and challenge:
        try:
            return int(challenge)
        except ValueError:
            return challenge
    return JSONResponse(status_code=403, content={"error": "Verification failed"})


@fastapi_app.post("/webhook/whatsapp")
async def wa_webhook(request: Request):
    """Receive inbound WhatsApp messages from Meta."""
    from services.wa_webhook import verify_signature, process_webhook_payload
    from services.database import get_db

    payload_bytes = await request.body()
    signature = request.headers.get("X-Hub-Signature-256", "")

    if not verify_signature(payload_bytes, signature):
        return JSONResponse(status_code=403, content={"error": "Invalid signature"})

    payload = await request.json()
    db = get_db()
    try:
        result = process_webhook_payload(db, payload)
        return JSONResponse(content={"status": "ok", **result})
    except Exception as e:
        log.exception("Webhook processing error")
        return JSONResponse(status_code=500, content={"error": str(e)})
    finally:
        db.close()


@fastapi_app.get("/health")
async def health():
    return {"status": "ok", "service": "himalayan-fibers-dashboard"}


# -- Background thread for flow automation --
def _flow_automation_loop():
    """Check pending flow steps every 30 minutes."""
    while True:
        time.sleep(1800)  # 30 minutes
        try:
            from services.database import get_db
            from services.flows_engine import check_pending_steps
            db = get_db()
            try:
                executed = check_pending_steps(db)
                if executed:
                    log.info("Flow automation: executed %d pending steps", executed)
            finally:
                db.close()
        except Exception:
            log.exception("Flow automation error")


_flow_thread = threading.Thread(target=_flow_automation_loop, daemon=True)
_flow_thread.start()

# -- Gradio app --
demo = build_app_with_sidebar(title="Himalayan Fibers")

# -- Mount Gradio onto FastAPI with theme + CSS --
from shared.theme import build_theme
from shared.theme_css import DASHBOARD_CSS

app = gr.mount_gradio_app(
    fastapi_app,
    demo,
    path="/",
    theme=build_theme(),
    css=DASHBOARD_CSS,
)


if __name__ == "__main__":
    import uvicorn
    # Reload disabled in dev: WatchFiles triggering mid-session restarts
    # orphans Gradio's SSE queue and leaves components stuck on "processing".
    # Restart the server manually after code changes.
    uvicorn.run("app:app", host="0.0.0.0", port=7860, reload=False)
