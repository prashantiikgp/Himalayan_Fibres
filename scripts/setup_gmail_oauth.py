"""One-time Gmail OAuth setup for the v2 HF Space.

Reads GMAIL_CLIENT_ID + GMAIL_CLIENT_SECRET from the repo .env, walks
through Google's consent flow with the gmail.send scope, captures the
refresh token, and pushes all three values to the v2 Space as Secrets.

Run once:
    ! python scripts/setup_gmail_oauth.py

The `!` prefix runs it in your terminal session so the browser-based
consent flow lands its redirect on http://localhost:<port>.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

try:
    from dotenv import load_dotenv  # type: ignore[import-not-found]

    load_dotenv(REPO_ROOT / ".env")
except ImportError:
    pass


SCOPES = ["https://www.googleapis.com/auth/gmail.send"]
SPACE_REPO_ID = "Prashantiitkgp08/Himalayan_Fibrer_v2"


def main() -> int:
    client_id = (os.getenv("GMAIL_CLIENT_ID") or "").strip()
    client_secret = (os.getenv("GMAIL_CLIENT_SECRET") or "").strip()
    if not client_id or not client_secret:
        print(
            "ERROR: set GMAIL_CLIENT_ID and GMAIL_CLIENT_SECRET in .env first.",
            file=sys.stderr,
        )
        return 1

    # google-auth-oauthlib's InstalledAppFlow can take a client_config
    # dict directly — no need for a JSON file on disk.
    from google_auth_oauthlib.flow import InstalledAppFlow

    client_config = {
        "installed": {
            "client_id": client_id,
            "client_secret": client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": ["http://localhost"],
        }
    }

    flow = InstalledAppFlow.from_client_config(client_config, SCOPES)
    print("Opening browser for Google consent…")
    print("Tip: pick the gmail account you want to send FROM.\n")
    creds = flow.run_local_server(
        port=0,
        prompt="consent",
        access_type="offline",
        open_browser=True,
    )

    refresh_token = (creds.refresh_token or "").strip()
    if not refresh_token:
        print(
            "ERROR: refresh_token came back empty. This usually means the "
            "Google account already authorized this OAuth client. Revoke it "
            "at https://myaccount.google.com/permissions and re-run.",
            file=sys.stderr,
        )
        return 2

    print("\n✓ Got refresh_token (length:", len(refresh_token), "chars)")

    # Push to v2 Space.
    hf_token = (os.getenv("HF_TOKEN") or os.getenv("HUGGINGFACE_TOKEN") or "").strip()
    if not hf_token:
        try:
            from huggingface_hub import get_token as _hf_get_token  # type: ignore[import-not-found]

            hf_token = _hf_get_token() or ""
        except ImportError:
            pass
    if not hf_token:
        print(
            "ERROR: HF_TOKEN missing — refresh token captured but couldn't "
            "push it to the Space. You can paste it manually at:\n"
            f"  https://huggingface.co/spaces/{SPACE_REPO_ID}/settings",
            file=sys.stderr,
        )
        print("\nGMAIL_REFRESH_TOKEN =", refresh_token)
        return 3

    from huggingface_hub import HfApi  # type: ignore[import-not-found]

    api = HfApi(token=hf_token)
    api.add_space_secret(SPACE_REPO_ID, "GMAIL_CLIENT_ID", client_id)
    api.add_space_secret(SPACE_REPO_ID, "GMAIL_CLIENT_SECRET", client_secret)
    api.add_space_secret(SPACE_REPO_ID, "GMAIL_REFRESH_TOKEN", refresh_token)
    print(f"\n✓ Pushed GMAIL_CLIENT_ID / SECRET / REFRESH_TOKEN to {SPACE_REPO_ID}")
    print("  The Space will restart automatically.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
