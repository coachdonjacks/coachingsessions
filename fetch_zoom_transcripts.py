#!/usr/bin/env python3
"""
fetch_zoom_transcripts.py

Pulls cloud recording transcripts directly from Zoom for the past 7 days
and saves them as .txt files in ./transcripts/ for process_transcripts.py.

This uses Zoom's standard user-level OAuth — no admin access required.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ONE-TIME SETUP (takes about 5 minutes)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

1. Go to https://marketplace.zoom.us
   (Sign in with your Zoom account — the same one you use for meetings)

2. Click "Develop" (top right) → "Build App"

3. Choose "General App" → click "Create"
   - App Name: "Coaching Workflow"  (anything works)
   - Click "Create"

4. On the left sidebar click "Surface" → add "User-managed app"
   then on "Scopes" add these two scopes:
     • cloud_recording:read:list_user_recordings:admin
     OR simpler: search "recording" and add "View your recordings" scope

5. On the left sidebar click "Local Test" → copy:
     • Client ID
     • Client Secret
   Paste both into your .env file:
     ZOOM_CLIENT_ID=your_client_id
     ZOOM_CLIENT_SECRET=your_client_secret

6. Under "OAuth" settings, add this as a redirect URL:
     http://localhost:8080/callback

7. Run this script once to authorize:
     python3 fetch_zoom_transcripts.py --setup

   A browser window will open. Click "Allow".
   After that, transcripts will fetch automatically every week.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""

import json
import os
import re
import sys
import time
import webbrowser
from base64 import b64encode
from datetime import date, timedelta
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlparse

import requests
from dotenv import load_dotenv

load_dotenv()

TRANSCRIPTS_DIR = Path("transcripts")
TRANSCRIPTS_DIR.mkdir(exist_ok=True)

TOKEN_FILE = Path(".zoom_token.json")

ZOOM_AUTH_URL = "https://zoom.us/oauth/authorize"
ZOOM_TOKEN_URL = "https://zoom.us/oauth/token"
ZOOM_API_BASE = "https://api.zoom.us/v2"
REDIRECT_URI = "http://localhost:8080/callback"


# ---------------------------------------------------------------------------
# OAuth token management
# ---------------------------------------------------------------------------

def _client_creds() -> tuple[str, str]:
    client_id = os.getenv("ZOOM_CLIENT_ID")
    client_secret = os.getenv("ZOOM_CLIENT_SECRET")
    if not client_id or not client_secret:
        sys.exit(
            "ERROR: ZOOM_CLIENT_ID and ZOOM_CLIENT_SECRET must be set in .env\n"
            "See the setup instructions at the top of this file."
        )
    return client_id, client_secret


def _save_token(token_data: dict) -> None:
    TOKEN_FILE.write_text(json.dumps(token_data, indent=2), encoding="utf-8")


def _load_token() -> dict | None:
    if TOKEN_FILE.exists():
        try:
            return json.loads(TOKEN_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    return None


def _refresh_access_token(refresh_token: str) -> dict:
    client_id, client_secret = _client_creds()
    credentials = b64encode(f"{client_id}:{client_secret}".encode()).decode()
    resp = requests.post(
        ZOOM_TOKEN_URL,
        params={"grant_type": "refresh_token", "refresh_token": refresh_token},
        headers={"Authorization": f"Basic {credentials}"},
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()


def get_access_token() -> str:
    """
    Return a valid access token.
    Uses cached refresh token if available; prompts for auth if not.
    """
    token_data = _load_token()

    if token_data and token_data.get("refresh_token"):
        try:
            new_data = _refresh_access_token(token_data["refresh_token"])
            _save_token(new_data)
            return new_data["access_token"]
        except requests.HTTPError as e:
            if e.response.status_code in (400, 401):
                print("Saved Zoom token has expired. Re-authorizing...")
                TOKEN_FILE.unlink(missing_ok=True)
            else:
                raise

    # No token (or expired) — run the OAuth flow
    return _run_oauth_flow()


def _run_oauth_flow() -> str:
    """
    Open a browser for Zoom OAuth authorization and capture the code
    via a local HTTP server.  Returns a fresh access token.
    """
    client_id, client_secret = _client_creds()

    auth_params = {
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": REDIRECT_URI,
    }
    auth_url = f"{ZOOM_AUTH_URL}?{urlencode(auth_params)}"

    # ── Capture the redirect code via a tiny local server ──────────────
    captured = {}

    class _Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            parsed = urlparse(self.path)
            params = parse_qs(parsed.query)
            if "code" in params:
                captured["code"] = params["code"][0]
                self.send_response(200)
                self.end_headers()
                self.wfile.write(
                    b"<html><body><h2>Authorization successful!</h2>"
                    b"<p>You can close this tab and return to the terminal.</p>"
                    b"</body></html>"
                )
            else:
                self.send_response(400)
                self.end_headers()
                self.wfile.write(b"<html><body>Authorization failed.</body></html>")

        def log_message(self, *args):
            pass  # silence server log spam

    print("\n" + "=" * 60)
    print("  ZOOM AUTHORIZATION REQUIRED")
    print("=" * 60)
    print("\nOpening your browser to authorize Zoom access...")
    print("(If the browser doesn't open, go to this URL manually:)")
    print(f"\n  {auth_url}\n")

    webbrowser.open(auth_url)

    server = HTTPServer(("localhost", 8080), _Handler)
    server.timeout = 120  # 2 minutes to complete auth
    print("Waiting for authorization (timeout: 2 minutes)...")
    server.handle_request()

    if "code" not in captured:
        sys.exit("ERROR: Did not receive authorization code. Please try again.")

    # ── Exchange code for tokens ────────────────────────────────────────
    credentials = b64encode(f"{client_id}:{client_secret}".encode()).decode()
    resp = requests.post(
        ZOOM_TOKEN_URL,
        params={
            "grant_type": "authorization_code",
            "code": captured["code"],
            "redirect_uri": REDIRECT_URI,
        },
        headers={"Authorization": f"Basic {credentials}"},
        timeout=15,
    )
    resp.raise_for_status()
    token_data = resp.json()
    _save_token(token_data)

    print("\nAuthorization successful! Token saved.")
    print("You won't need to do this again (tokens refresh automatically).\n")
    return token_data["access_token"]


# ---------------------------------------------------------------------------
# Zoom API helpers
# ---------------------------------------------------------------------------

def list_recordings(token: str, from_date: str, to_date: str) -> list[dict]:
    """Return all cloud recording meetings in the given date range."""
    headers = {"Authorization": f"Bearer {token}"}
    meetings = []
    next_page_token = None

    while True:
        params = {"from": from_date, "to": to_date, "page_size": 300}
        if next_page_token:
            params["next_page_token"] = next_page_token

        resp = requests.get(
            f"{ZOOM_API_BASE}/users/me/recordings",
            headers=headers,
            params=params,
            timeout=20,
        )
        resp.raise_for_status()
        data = resp.json()
        meetings.extend(data.get("meetings", []))

        next_page_token = data.get("next_page_token")
        if not next_page_token:
            break

    return meetings


def find_transcript_file(meeting: dict) -> dict | None:
    """Return the completed VTT transcript file from a recording, or None."""
    for f in meeting.get("recording_files", []):
        if f.get("file_type", "").upper() == "TRANSCRIPT" and f.get("status") == "completed":
            return f
    return None


def download_vtt(download_url: str, token: str) -> str:
    """Download a Zoom VTT transcript file (access token passed as query param)."""
    resp = requests.get(
        download_url,
        params={"access_token": token},
        timeout=60,
    )
    resp.raise_for_status()
    return resp.text


def vtt_to_text(vtt_content: str) -> str:
    """
    Convert WebVTT to clean plain text.
    Strips timestamps, cue IDs, and HTML tags; deduplicates repeated lines.
    """
    timestamp_re = re.compile(r"^\d{2}:\d{2}:\d{2}\.\d{3}\s*-->\s*\d{2}:\d{2}:\d{2}\.\d{3}")
    text_lines = []

    for line in vtt_content.splitlines():
        line = line.strip()
        if not line or line == "WEBVTT":
            continue
        if timestamp_re.match(line):
            continue
        if line.isdigit():
            continue
        # Strip HTML tags Zoom embeds (e.g. <v Speaker Name>)
        line = re.sub(r"<[^>]+>", "", line).strip()
        if line:
            text_lines.append(line)

    # Remove consecutive duplicate lines
    merged = []
    for line in text_lines:
        if not merged or merged[-1] != line:
            merged.append(line)

    return "\n".join(merged)


def safe_filename(meeting: dict) -> str:
    """Build a filesystem-safe filename from meeting metadata."""
    topic = meeting.get("topic", "session")
    start = meeting.get("start_time", "")[:10]
    meeting_id = str(meeting.get("id", ""))

    safe_topic = re.sub(r"[^\w\s-]", "", topic).strip()
    safe_topic = re.sub(r"\s+", "_", safe_topic)[:50]

    return f"{start}_{safe_topic}_{meeting_id}.txt"


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def fetch_transcripts(days: int = 7, from_date: str | None = None, to_date: str | None = None) -> int:
    """
    Download all Zoom cloud transcripts for the past `days` days.
    Returns count of files saved.
    """
    if to_date is None:
        to_date = date.today().isoformat()
    if from_date is None:
        from_date = (date.today() - timedelta(days=days)).isoformat()

    print(f"\nConnecting to Zoom...")
    token = get_access_token()

    print(f"Fetching recordings from {from_date} to {to_date}...")
    meetings = list_recordings(token, from_date, to_date)
    print(f"Found {len(meetings)} recording(s) in date range.\n")

    saved = 0
    skipped = 0

    for meeting in meetings:
        topic = meeting.get("topic", "(no topic)")
        start = meeting.get("start_time", "")[:10]

        transcript_file = find_transcript_file(meeting)
        if not transcript_file:
            print(f"  SKIP   [{start}] {topic[:60]}  — no transcript available")
            skipped += 1
            continue

        filename = safe_filename(meeting)
        out_path = TRANSCRIPTS_DIR / filename

        if out_path.exists():
            print(f"  EXISTS [{start}] {topic[:60]}")
            skipped += 1
            continue

        download_url = transcript_file.get("download_url", "")
        if not download_url:
            print(f"  SKIP   [{start}] {topic[:60]}  — missing download URL")
            skipped += 1
            continue

        try:
            vtt_content = download_vtt(download_url, token)
        except requests.HTTPError as e:
            if e.response.status_code == 401:
                # Token expired mid-batch — refresh once and retry
                token = get_access_token()
                vtt_content = download_vtt(download_url, token)
            else:
                print(f"  ERROR  [{start}] {topic[:60]}  — {e}")
                skipped += 1
                continue

        plain_text = vtt_to_text(vtt_content)

        if len(plain_text.strip()) < 50:
            print(f"  SKIP   [{start}] {topic[:60]}  — transcript too short after parsing")
            skipped += 1
            continue

        # Prepend session metadata so Claude has context
        header = (
            f"Coaching Session Transcript\n"
            f"Topic: {topic}\n"
            f"Date: {start}\n"
            f"Duration: {meeting.get('duration', '?')} minutes\n"
            f"{'=' * 60}\n\n"
        )
        out_path.write_text(header + plain_text, encoding="utf-8")
        print(f"  SAVED  [{start}] {topic[:60]}")
        print(f"          → {filename}")
        saved += 1

        time.sleep(0.2)  # polite to the Zoom API

    print(f"\nDone. {saved} transcript(s) saved, {skipped} skipped.")
    if saved > 0:
        print(f"Transcripts saved to: ./{TRANSCRIPTS_DIR}/")
        print("Next step: run  python process_transcripts.py")
    return saved


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Pull Zoom cloud recording transcripts for the past week."
    )
    parser.add_argument(
        "--days", type=int, default=7,
        help="How many days back to fetch (default: 7)"
    )
    parser.add_argument(
        "--from", dest="from_date", default=None,
        help="Start date YYYY-MM-DD (overrides --days)"
    )
    parser.add_argument(
        "--to", dest="to_date", default=None,
        help="End date YYYY-MM-DD (default: today)"
    )
    parser.add_argument(
        "--setup", action="store_true",
        help="Run the one-time Zoom authorization flow"
    )
    args = parser.parse_args()

    if args.setup:
        TOKEN_FILE.unlink(missing_ok=True)
        print("Starting Zoom authorization...")
        get_access_token()
        print("Setup complete! Run  python fetch_zoom_transcripts.py  to fetch transcripts.")
    else:
        fetch_transcripts(days=args.days, from_date=args.from_date, to_date=args.to_date)
