#!/usr/bin/env python3
"""
fetch_email_summaries.py

Connects to your Gmail (or Google Workspace) inbox via IMAP,
finds all Zoom meeting summary emails from the past 7 days,
extracts the summary text, and saves each one as a .txt file
in ./transcripts/ for process_transcripts.py to pick up.

Setup (one-time):
  1. Enable IMAP in Gmail:
     Gmail → Settings (gear) → See all settings → Forwarding and POP/IMAP
     → IMAP access → Enable IMAP → Save

  2. Create a Gmail App Password:
     myaccount.google.com → Security → 2-Step Verification (enable if not on)
     → App passwords → create one named "Coaching Workflow"
     → Copy the 16-character password into .env as GMAIL_APP_PASSWORD

  3. Add to .env:
     GMAIL_ADDRESS=djacks@yourcoach.com
     GMAIL_APP_PASSWORD=xxxx xxxx xxxx xxxx
"""

import email
import imaplib
import os
import re
import sys
import time
from datetime import date, timedelta
from email.header import decode_header
from html.parser import HTMLParser
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

TRANSCRIPTS_DIR = Path("transcripts")
TRANSCRIPTS_DIR.mkdir(exist_ok=True)

GMAIL_IMAP_HOST = "imap.gmail.com"
GMAIL_IMAP_PORT = 993

# Zoom sends summaries from these sender domains/addresses
ZOOM_SENDERS = ["zoom.us", "no-reply@zoom.us", "noreply@zoom.us"]

# Subject keywords that indicate a Zoom summary email
ZOOM_SUBJECT_KEYWORDS = [
    "meeting summary",
    "ai summary",
    "ai companion",
    "zoom summary",
    "coaching summary",
    "session summary",
]


# ---------------------------------------------------------------------------
# HTML → plain text helper
# ---------------------------------------------------------------------------

class _HTMLStripper(HTMLParser):
    def __init__(self):
        super().__init__()
        self.reset()
        self._chunks = []
        self._skip_tags = {"script", "style", "head"}
        self._current_skip = False

    def handle_starttag(self, tag, attrs):
        if tag.lower() in self._skip_tags:
            self._current_skip = True
        if tag.lower() in {"br", "p", "div", "tr", "li", "h1", "h2", "h3", "h4"}:
            self._chunks.append("\n")

    def handle_endtag(self, tag):
        if tag.lower() in self._skip_tags:
            self._current_skip = False

    def handle_data(self, data):
        if not self._current_skip:
            self._chunks.append(data)

    def get_text(self) -> str:
        text = "".join(self._chunks)
        # Collapse excessive blank lines
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()


def html_to_text(html: str) -> str:
    stripper = _HTMLStripper()
    stripper.feed(html)
    return stripper.get_text()


# ---------------------------------------------------------------------------
# Email parsing
# ---------------------------------------------------------------------------

def decode_mime_header(value: str) -> str:
    """Decode encoded email header value to plain string."""
    if not value:
        return ""
    parts = decode_header(value)
    decoded = []
    for part, charset in parts:
        if isinstance(part, bytes):
            decoded.append(part.decode(charset or "utf-8", errors="replace"))
        else:
            decoded.append(part)
    return " ".join(decoded)


def extract_body(msg) -> str:
    """
    Extract best available plain-text body from an email.Message.
    Prefers text/plain; falls back to HTML-stripped text/html.
    """
    plain = None
    html = None

    if msg.is_multipart():
        for part in msg.walk():
            ct = part.get_content_type()
            disposition = str(part.get("Content-Disposition", ""))
            if "attachment" in disposition:
                continue
            if ct == "text/plain" and plain is None:
                raw = part.get_payload(decode=True)
                if raw:
                    plain = raw.decode(part.get_content_charset() or "utf-8", errors="replace")
            elif ct == "text/html" and html is None:
                raw = part.get_payload(decode=True)
                if raw:
                    html = raw.decode(part.get_content_charset() or "utf-8", errors="replace")
    else:
        raw = msg.get_payload(decode=True)
        ct = msg.get_content_type()
        if raw:
            text = raw.decode(msg.get_content_charset() or "utf-8", errors="replace")
            if ct == "text/html":
                html = text
            else:
                plain = text

    if plain:
        return plain.strip()
    if html:
        return html_to_text(html)
    return ""


def is_zoom_summary(subject: str, sender: str) -> bool:
    """Return True if this email looks like a Zoom meeting summary."""
    subject_lower = subject.lower()
    sender_lower = sender.lower()

    from_zoom = any(z in sender_lower for z in ZOOM_SENDERS)
    subject_match = any(kw in subject_lower for kw in ZOOM_SUBJECT_KEYWORDS)

    return from_zoom or subject_match


def safe_filename(subject: str, msg_date: str) -> str:
    """Build a safe filename from the email subject and date."""
    # Strip common Zoom prefix noise
    clean = re.sub(r"(?i)^(re:|fwd?:|zoom\s+)?meeting\s+summary[:\s-]*", "", subject).strip()
    clean = re.sub(r"[^\w\s-]", "", clean).strip()
    clean = re.sub(r"\s+", "_", clean)[:60]
    date_str = msg_date[:10] if msg_date else date.today().isoformat()
    return f"{date_str}_{clean}.txt"


# ---------------------------------------------------------------------------
# Gmail IMAP
# ---------------------------------------------------------------------------

def connect(address: str, app_password: str) -> imaplib.IMAP4_SSL:
    mail = imaplib.IMAP4_SSL(GMAIL_IMAP_HOST, GMAIL_IMAP_PORT)
    try:
        mail.login(address, app_password)
    except imaplib.IMAP4.error as e:
        sys.exit(
            f"ERROR: Gmail login failed — {e}\n\n"
            "Check that:\n"
            "  1. IMAP is enabled in Gmail Settings → Forwarding and POP/IMAP\n"
            "  2. GMAIL_APP_PASSWORD in .env is your 16-character App Password\n"
            "     (not your regular Gmail password)\n"
            "  Create one at: myaccount.google.com → Security → App passwords"
        )
    return mail


def search_zoom_emails(mail: imaplib.IMAP4_SSL, days: int) -> list[bytes]:
    """Return list of email UIDs matching Zoom summary criteria."""
    mail.select("INBOX")

    since_date = (date.today() - timedelta(days=days)).strftime("%d-%b-%Y")

    # Search all recent emails from Zoom's domain
    _, zoom_data = mail.search(None, f'SINCE {since_date} FROM "zoom.us"')
    zoom_ids = zoom_data[0].split() if zoom_data[0] else []

    # Also search by common subject keywords (catches custom sender configs)
    keyword_ids = []
    for keyword in ["Meeting Summary", "AI Summary", "AI Companion", "Coaching Summary"]:
        _, kw_data = mail.search(None, f'SINCE {since_date} SUBJECT "{keyword}"')
        if kw_data[0]:
            keyword_ids.extend(kw_data[0].split())

    # Deduplicate
    all_ids = list({uid for uid in zoom_ids + keyword_ids})
    return all_ids


def fetch_summaries(days: int = 7) -> int:
    """
    Fetch Zoom summary emails from Gmail and save as transcripts.
    Returns count of files saved.
    """
    gmail_address = os.getenv("GMAIL_ADDRESS")
    app_password = os.getenv("GMAIL_APP_PASSWORD")

    if not gmail_address or not app_password:
        sys.exit(
            "ERROR: GMAIL_ADDRESS and GMAIL_APP_PASSWORD must be set in .env\n"
            "See the instructions at the top of this file."
        )

    print(f"\nConnecting to Gmail as {gmail_address}...")
    mail = connect(gmail_address, app_password)

    print(f"Searching for Zoom summary emails from the past {days} days...")
    email_ids = search_zoom_emails(mail, days)

    print(f"Found {len(email_ids)} matching email(s).\n")

    saved = 0
    skipped = 0

    for uid in email_ids:
        _, msg_data = mail.fetch(uid, "(RFC822)")
        if not msg_data or not msg_data[0]:
            continue

        raw = msg_data[0][1]
        msg = email.message_from_bytes(raw)

        subject = decode_mime_header(msg.get("Subject", "Zoom Summary"))
        sender = decode_mime_header(msg.get("From", ""))
        msg_date = msg.get("Date", "")[:16].strip()

        # Parse date to YYYY-MM-DD for filename
        try:
            from email.utils import parsedate_to_datetime
            dt = parsedate_to_datetime(msg.get("Date", ""))
            date_str = dt.date().isoformat()
        except Exception:
            date_str = date.today().isoformat()

        # Final check — skip if not actually a summary email
        if not is_zoom_summary(subject, sender):
            skipped += 1
            continue

        filename = safe_filename(subject, date_str)
        out_path = TRANSCRIPTS_DIR / filename

        if out_path.exists():
            print(f"  EXISTS  [{date_str}] {subject[:60]}")
            skipped += 1
            continue

        body = extract_body(msg)
        if len(body.strip()) < 50:
            print(f"  SKIP    [{date_str}] {subject[:60]}  — body too short")
            skipped += 1
            continue

        # Prepend metadata header for Claude context
        header = (
            f"Coaching Session Summary\n"
            f"Subject: {subject}\n"
            f"Date: {date_str}\n"
            f"{'=' * 60}\n\n"
        )
        out_path.write_text(header + body, encoding="utf-8")
        print(f"  SAVED   [{date_str}] {subject[:60]}")
        print(f"           → {filename}")
        saved += 1

        time.sleep(0.1)  # be polite to IMAP

    mail.logout()

    print(f"\nDone. {saved} summary/summaries saved, {skipped} skipped.")
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
        description="Pull Zoom meeting summary emails from Gmail."
    )
    parser.add_argument(
        "--days",
        type=int,
        default=7,
        help="How many days back to look (default: 7)",
    )
    args = parser.parse_args()

    fetch_summaries(days=args.days)
