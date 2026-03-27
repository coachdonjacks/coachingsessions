#!/usr/bin/env python3
"""
fetch_zoom_transcripts.py

Pulls cloud recording transcripts from Zoom for the past 7 days
(or a custom date range) and saves them as .txt files in ./transcripts/
ready for process_transcripts.py to pick up.

Requirements:
  - A Zoom Server-to-Server OAuth app (free to create at marketplace.zoom.us)
  - Cloud Recording + Audio Transcript enabled in your Zoom account settings
  - Scopes: recording:read:admin  (or recording:read for single-user)

Setup (one-time):
  1. Go to https://marketplace.zoom.us → Develop → Build App → Server-to-Server OAuth
  2. Copy your Account ID, Client ID, Client Secret into .env
  3. Under Scopes, add: recording:read:admin
  4. Activate the app
"""

import os
import re
import sys
import time
from base64 import b64encode
from datetime import date, datetime, timedelta
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv()

TRANSCRIPTS_DIR = Path("transcripts")
TRANSCRIPTS_DIR.mkdir(exist_ok=True)

ZOOM_OAUTH_URL = "https://zoom.us/oauth/token"
ZOOM_API_BASE = "https://api.zoom.us/v2"


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

def get_access_token() -> str:
    """Obtain a short-lived access token via Server-to-Server OAuth."""
    account_id = os.getenv("ZOOM_ACCOUNT_ID")
    client_id = os.getenv("ZOOM_CLIENT_ID")
    client_secret = os.getenv("ZOOM_CLIENT_SECRET")

    if not all([account_id, client_id, client_secret]):
        sys.exit(
            "ERROR: ZOOM_ACCOUNT_ID, ZOOM_CLIENT_ID, and ZOOM_CLIENT_SECRET must be set in .env\n"
            "See README for how to create a Zoom Server-to-Server OAuth app."
        )

    credentials = b64encode(f"{client_id}:{client_secret}".encode()).decode()
    resp = requests.post(
        ZOOM_OAUTH_URL,
        params={"grant_type": "account_credentials", "account_id": account_id},
        headers={"Authorization": f"Basic {credentials}"},
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()["access_token"]


# ---------------------------------------------------------------------------
# Zoom API helpers
# ---------------------------------------------------------------------------

def list_recordings(token: str, from_date: str, to_date: str) -> list[dict]:
    """
    List all cloud recordings in the given date range.
    from_date / to_date: 'YYYY-MM-DD'
    Returns a flat list of meeting recording objects.
    """
    headers = {"Authorization": f"Bearer {token}"}
    meetings = []
    next_page_token = None

    while True:
        params = {
            "from": from_date,
            "to": to_date,
            "page_size": 300,
        }
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
    """Return the transcript recording file object, or None if absent."""
    for f in meeting.get("recording_files", []):
        if f.get("file_type", "").upper() == "TRANSCRIPT" and f.get("status") == "completed":
            return f
    return None


def download_vtt(download_url: str, token: str) -> str:
    """Download VTT content from Zoom (requires auth token in URL or header)."""
    # Zoom requires the token as a query param for direct file downloads
    resp = requests.get(
        download_url,
        params={"access_token": token},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.text


def vtt_to_text(vtt_content: str) -> str:
    """
    Convert a WebVTT transcript to clean plain text.
    Strips timestamps, cue identifiers, and VTT headers.
    Merges speaker lines intelligently.
    """
    lines = vtt_content.splitlines()
    text_lines = []
    timestamp_pattern = re.compile(r"^\d{2}:\d{2}:\d{2}\.\d{3}\s*-->\s*\d{2}:\d{2}:\d{2}\.\d{3}")

    for line in lines:
        line = line.strip()
        if not line:
            continue
        if line == "WEBVTT":
            continue
        if timestamp_pattern.match(line):
            continue
        # Skip pure numeric cue IDs
        if line.isdigit():
            continue
        # Strip HTML tags Zoom sometimes embeds
        line = re.sub(r"<[^>]+>", "", line).strip()
        if line:
            text_lines.append(line)

    # Merge consecutive identical speaker labels
    merged = []
    for line in text_lines:
        if merged and merged[-1] == line:
            continue
        merged.append(line)

    return "\n".join(merged)


def safe_filename(meeting: dict) -> str:
    """Build a safe, descriptive filename from meeting metadata."""
    topic = meeting.get("topic", "session")
    start = meeting.get("start_time", "")[:10]  # YYYY-MM-DD
    meeting_id = meeting.get("id", "")

    # Sanitize topic for use in filename
    safe_topic = re.sub(r"[^\w\s-]", "", topic).strip()
    safe_topic = re.sub(r"\s+", "_", safe_topic)[:50]

    return f"{start}_{safe_topic}_{meeting_id}.txt"


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def fetch_transcripts(days: int = 7, from_date: str | None = None, to_date: str | None = None) -> int:
    """
    Download all Zoom transcripts from the past `days` days (default: 7).
    Returns the count of transcripts saved.
    """
    if to_date is None:
        to_date = date.today().isoformat()
    if from_date is None:
        from_date = (date.today() - timedelta(days=days)).isoformat()

    print(f"\nFetching Zoom transcripts from {from_date} to {to_date}...")

    token = get_access_token()
    meetings = list_recordings(token, from_date, to_date)

    print(f"Found {len(meetings)} recording(s) in range.")

    saved = 0
    skipped = 0

    for meeting in meetings:
        topic = meeting.get("topic", "(no topic)")
        start = meeting.get("start_time", "")[:10]

        transcript_file = find_transcript_file(meeting)
        if not transcript_file:
            print(f"  SKIP  [{start}] {topic}  — no completed transcript")
            skipped += 1
            continue

        filename = safe_filename(meeting)
        out_path = TRANSCRIPTS_DIR / filename

        if out_path.exists():
            print(f"  EXISTS [{start}] {topic}  → {filename}")
            skipped += 1
            continue

        download_url = transcript_file.get("download_url", "")
        if not download_url:
            print(f"  SKIP  [{start}] {topic}  — missing download URL")
            skipped += 1
            continue

        # Refresh token for each download to avoid expiry on large batches
        try:
            vtt_content = download_vtt(download_url, token)
        except requests.HTTPError as e:
            if e.response.status_code == 401:
                # Token expired — refresh and retry once
                token = get_access_token()
                vtt_content = download_vtt(download_url, token)
            else:
                print(f"  ERROR [{start}] {topic}  — {e}")
                skipped += 1
                continue

        plain_text = vtt_to_text(vtt_content)

        if len(plain_text.strip()) < 50:
            print(f"  SKIP  [{start}] {topic}  — transcript appears empty after parsing")
            skipped += 1
            continue

        # Prepend meeting metadata as context for Claude
        header = (
            f"Coaching Session Transcript\n"
            f"Topic: {topic}\n"
            f"Date: {start}\n"
            f"Duration: {meeting.get('duration', '?')} minutes\n"
            f"{'=' * 60}\n\n"
        )
        out_path.write_text(header + plain_text, encoding="utf-8")
        print(f"  SAVED [{start}] {topic}  → {filename}")
        saved += 1

        # Be polite to the API
        time.sleep(0.2)

    print(f"\nDone. {saved} transcript(s) saved, {skipped} skipped.")
    print(f"Transcripts are in: ./{TRANSCRIPTS_DIR}/")
    if saved > 0:
        print("Next step: run  python process_transcripts.py  to extract insights.")
    return saved


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Pull Zoom cloud recording transcripts for the past week."
    )
    parser.add_argument(
        "--days",
        type=int,
        default=7,
        help="How many days back to fetch (default: 7)",
    )
    parser.add_argument(
        "--from",
        dest="from_date",
        help="Start date YYYY-MM-DD (overrides --days)",
        default=None,
    )
    parser.add_argument(
        "--to",
        dest="to_date",
        help="End date YYYY-MM-DD (default: today)",
        default=None,
    )
    args = parser.parse_args()

    fetch_transcripts(days=args.days, from_date=args.from_date, to_date=args.to_date)
