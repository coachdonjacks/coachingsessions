#!/usr/bin/env python3
"""
run_weekly.py

One command to run the full weekly coaching workflow:
  1. Fetch Zoom summary emails from Gmail
  2. Extract per-session insights with Claude
  3. Synthesize into a weekly email with Claude
  4. Send the email via Gmail SMTP
  5. Archive processed transcripts

Usage:
    python run_weekly.py                        # full run, sends email
    python run_weekly.py --no-send              # generate only, don't send
    python run_weekly.py --days 14              # look back 14 days
    python run_weekly.py --to me@example.com    # override recipient
"""

import argparse
import os
import shutil
import smtplib
import sys
from datetime import date
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

TRANSCRIPTS_DIR = Path("transcripts")
ARCHIVE_DIR = Path("transcripts/archive")
OUTPUT_DIR = Path("output")

GMAIL_SMTP_HOST = "smtp.gmail.com"
GMAIL_SMTP_PORT = 587


# ---------------------------------------------------------------------------
# Email sending
# ---------------------------------------------------------------------------

def send_email(subject: str, body_text: str, body_html: str, recipient: str) -> None:
    """Send the weekly email via Gmail SMTP using the same App Password."""
    gmail_address = os.getenv("GMAIL_ADDRESS")
    app_password = os.getenv("GMAIL_APP_PASSWORD")
    coach_name = os.getenv("COACH_NAME", "Coach")

    if not gmail_address or not app_password:
        sys.exit("ERROR: GMAIL_ADDRESS and GMAIL_APP_PASSWORD must be set in .env")

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = f"{coach_name} <{gmail_address}>"
    msg["To"] = recipient

    msg.attach(MIMEText(body_text, "plain"))
    msg.attach(MIMEText(body_html, "html"))

    print(f"\nSending email to {recipient}...")
    try:
        with smtplib.SMTP(GMAIL_SMTP_HOST, GMAIL_SMTP_PORT) as server:
            server.ehlo()
            server.starttls()
            server.login(gmail_address, app_password)
            server.sendmail(gmail_address, recipient, msg.as_string())
        print(f"  Email sent to {recipient}")
    except smtplib.SMTPAuthenticationError:
        sys.exit(
            "ERROR: Gmail SMTP authentication failed.\n"
            "Make sure GMAIL_APP_PASSWORD is your 16-character App Password.\n"
            "Create one at: myaccount.google.com → Security → App passwords"
        )
    except Exception as e:
        sys.exit(f"ERROR: Failed to send email — {e}")


def extract_subject_from_email(text: str) -> str:
    """Pull the subject line Claude wrote out of the email body."""
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.upper().startswith("SUBJECT LINE:") or stripped.upper().startswith("SUBJECT:"):
            subject = stripped.split(":", 1)[-1].strip()
            # Strip surrounding brackets if present: [Subject here]
            subject = subject.strip("[]")
            if subject:
                return subject
    subject_prefix = os.getenv("EMAIL_SUBJECT_PREFIX", "Weekly Coaching Insights")
    return f"{subject_prefix} — Week of {date.today().strftime('%B %d, %Y')}"


# ---------------------------------------------------------------------------
# Archive
# ---------------------------------------------------------------------------

def archive_transcripts() -> int:
    """Move processed transcripts to transcripts/archive/."""
    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    moved = 0
    for f in TRANSCRIPTS_DIR.glob("*.txt"):
        dest = ARCHIVE_DIR / f.name
        # If same filename already in archive, add date suffix
        if dest.exists():
            dest = ARCHIVE_DIR / f"{f.stem}_{date.today().isoformat()}{f.suffix}"
        shutil.move(str(f), str(dest))
        moved += 1
    return moved


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def run(days: int = 7, send: bool = True, recipient: str | None = None) -> None:
    week_tag = date.today().strftime("%Y-W%W")

    print("=" * 60)
    print(f"  WEEKLY COACHING WORKFLOW  —  {date.today().strftime('%B %d, %Y')}")
    print("=" * 60)

    # ── Step 1: Fetch transcripts from Zoom ──────────────────────────
    print(f"\n[1/4] Fetching Zoom cloud transcripts (last {days} days)...")
    from fetch_zoom_transcripts import fetch_transcripts
    fetched = fetch_transcripts(days=days)

    transcript_count = len(list(TRANSCRIPTS_DIR.glob("*.txt")))
    if transcript_count == 0:
        print("\nNo transcripts found. Nothing to process.")
        print("Make sure Zoom AI Summary emails are in your inbox.")
        return

    # ── Step 2: Extract per-session insights ─────────────────────────
    print(f"\n[2/4] Extracting insights from {transcript_count} transcript(s) with Claude...")
    from process_transcripts import process_all_transcripts
    sessions = process_all_transcripts(week_label=week_tag)

    if not sessions:
        print("\nNo sessions processed. Check transcripts/ folder.")
        return

    # ── Step 3: Generate weekly email ────────────────────────────────
    print(f"\n[3/4] Synthesizing {len(sessions)} session(s) into weekly email...")
    from generate_weekly_email import generate_weekly_email
    generate_weekly_email(week_label=week_tag)

    # ── Step 4: Send email ────────────────────────────────────────────
    if send:
        txt_path = OUTPUT_DIR / "weekly" / f"{week_tag}_email.txt"
        html_path = OUTPUT_DIR / "weekly" / f"{week_tag}_email.html"

        if not txt_path.exists():
            print("ERROR: Email file not found. Skipping send.")
        else:
            body_text = txt_path.read_text(encoding="utf-8")
            body_html = html_path.read_text(encoding="utf-8") if html_path.exists() else body_text

            subject = extract_subject_from_email(body_text)
            to_address = recipient or os.getenv("EMAIL_RECIPIENT", os.getenv("GMAIL_ADDRESS"))

            print(f"\n[4/4] Sending email...")
            print(f"  Subject : {subject}")
            print(f"  To      : {to_address}")
            send_email(subject, body_text, body_html, to_address)
    else:
        print("\n[4/4] Skipping send (--no-send flag set).")
        print(f"  Email saved to: output/weekly/{week_tag}_email.txt")

    # ── Archive transcripts ───────────────────────────────────────────
    moved = archive_transcripts()
    print(f"\nArchived {moved} transcript(s) to transcripts/archive/")

    # ── Summary ──────────────────────────────────────────────────────
    print("\n" + "=" * 60)
    print(f"  DONE  —  {len(sessions)} sessions processed")
    if send:
        print(f"  Email sent to {recipient or os.getenv('EMAIL_RECIPIENT', os.getenv('GMAIL_ADDRESS'))}")
    print(f"  Review: output/weekly/{week_tag}_review_summary.json")
    print("=" * 60)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run the full weekly coaching workflow.")
    parser.add_argument("--days", type=int, default=7, help="Days back to fetch (default: 7)")
    parser.add_argument("--no-send", action="store_true", help="Generate email but don't send it")
    parser.add_argument("--to", dest="recipient", default=None, help="Override email recipient")
    args = parser.parse_args()

    run(days=args.days, send=not args.no_send, recipient=args.recipient)
