#!/usr/bin/env python3
"""
generate_weekly_email.py

Step 2 of the coaching workflow:
  - Reads all per-session JSON files from ./output/ (produced by process_transcripts.py)
  - Uses Claude to synthesize across all sessions: find patterns, recurring themes, top analogies
  - Produces a polished weekly email (plain text + HTML) ready to send or copy-paste

Output: ./output/weekly/<week>_email.txt and ./output/weekly/<week>_email.html
"""

import json
import os
import sys
from datetime import date
from pathlib import Path

import anthropic
from dotenv import load_dotenv

load_dotenv()

OUTPUT_DIR = Path("output")
WEEKLY_DIR = OUTPUT_DIR / "weekly"
WEEKLY_DIR.mkdir(parents=True, exist_ok=True)

SYNTHESIS_PROMPT = """You are a world-class coaching communications writer.
The coach has completed {session_count} coaching sessions this week.
Below is the aggregated data extracted from all sessions.

Your job: write a compelling weekly coaching insights email that the coach can send to their entire client community.

AGGREGATED SESSION DATA:
{aggregated_data}

Write the email with this structure:

---
SUBJECT LINE: [an engaging subject line the coach can use]

OPENING (2-3 sentences): A warm, energizing hook that frames the week's theme without sounding generic.

THIS WEEK'S TOP THEMES (3-5 bullet points):
Each bullet = one recurring topic seen across multiple sessions.
Format: **Theme Name** — 1-2 sentence insight that applies broadly to any reader.

COACHING ANALOGY OF THE WEEK:
Pick the single most powerful or universal analogy/story from this week's sessions.
Write it out as a 3-5 sentence mini-story that any reader can relate to and learn from.

ACTION ITEMS FOR YOU (3-5 bullets):
Distill the most common action items into universal challenges the reader can apply TODAY.
Make them specific and motivating, not vague.

CLOSING (2-3 sentences): Encouragement, call to reflection, and the coach's sign-off energy.
---

Tone: Direct, warm, motivating. Like a trusted mentor who tells you the truth with care.
Avoid: corporate speak, filler phrases, generic motivational clichés.
Length: Aim for 400-600 words total (scannable but substantive).
"""

HTML_WRAPPER = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<style>
  body {{ font-family: Georgia, serif; max-width: 640px; margin: 40px auto; color: #1a1a1a; line-height: 1.7; }}
  h2 {{ color: #1a3a5c; border-bottom: 2px solid #e0e0e0; padding-bottom: 8px; }}
  h3 {{ color: #2c5f8a; margin-top: 28px; }}
  ul {{ padding-left: 20px; }}
  li {{ margin-bottom: 8px; }}
  .analogy-box {{ background: #f4f8fc; border-left: 4px solid #2c5f8a; padding: 16px 20px; margin: 20px 0; border-radius: 0 6px 6px 0; }}
  .footer {{ margin-top: 36px; padding-top: 16px; border-top: 1px solid #e0e0e0; font-size: 0.9em; color: #555; }}
  strong {{ color: #1a3a5c; }}
</style>
</head>
<body>
{body}
</body>
</html>
"""


def aggregate_sessions(session_files: list[Path]) -> tuple[dict, int]:
    """Merge all session JSON files into one aggregated structure."""
    aggregated: dict[str, list] = {
        "main_topics": [],
        "key_takeaways": [],
        "analogies_used": [],
        "action_items": [],
        "emotional_themes": [],
        "notable_quotes": [],
    }

    session_count = 0
    for path in session_files:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as e:
            print(f"  WARNING: Could not read {path.name}: {e}")
            continue

        # Skip the combined-week file itself
        if isinstance(data, list):
            for session in data:
                for key in aggregated:
                    aggregated[key].extend(session.get(key, []))
            session_count += len(data)
        else:
            for key in aggregated:
                aggregated[key].extend(data.get(key, []))
            session_count += 1

    return aggregated, session_count


def synthesize_with_claude(client: anthropic.Anthropic, aggregated: dict, session_count: int) -> str:
    """Call Claude to synthesize all session data into a weekly email draft."""
    agg_text = json.dumps(aggregated, indent=2)

    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=2000,
        messages=[
            {
                "role": "user",
                "content": SYNTHESIS_PROMPT.format(
                    session_count=session_count,
                    aggregated_data=agg_text[:60000],
                ),
            }
        ],
    )

    return message.content[0].text.strip()


def text_to_simple_html(text: str) -> str:
    """Convert the plain-text email to basic HTML."""
    lines = text.split("\n")
    html_lines = []
    in_ul = False

    for line in lines:
        stripped = line.strip()
        if not stripped:
            if in_ul:
                html_lines.append("</ul>")
                in_ul = False
            html_lines.append("<br>")
            continue

        if stripped.startswith("SUBJECT LINE:"):
            html_lines.append(f"<h2>{stripped}</h2>")
        elif stripped.startswith("THIS WEEK'S TOP THEMES") or stripped.startswith("ACTION ITEMS") or stripped.startswith("COACHING ANALOGY"):
            if in_ul:
                html_lines.append("</ul>")
                in_ul = False
            html_lines.append(f"<h3>{stripped}</h3>")
        elif stripped.startswith("- ") or stripped.startswith("• "):
            if not in_ul:
                html_lines.append("<ul>")
                in_ul = True
            content = stripped[2:]
            # Bold **text**
            import re
            content = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", content)
            html_lines.append(f"<li>{content}</li>")
        else:
            if in_ul:
                html_lines.append("</ul>")
                in_ul = False
            import re
            line_html = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", stripped)
            html_lines.append(f"<p>{line_html}</p>")

    if in_ul:
        html_lines.append("</ul>")

    return HTML_WRAPPER.format(body="\n".join(html_lines))


def generate_weekly_email(week_label: str | None = None) -> None:
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        sys.exit("ERROR: ANTHROPIC_API_KEY not set. Copy .env.example to .env and add your key.")

    client = anthropic.Anthropic(api_key=api_key)
    week_tag = week_label or date.today().strftime("%Y-W%W")
    coach_name = os.getenv("COACH_NAME", "Coach")
    subject_prefix = os.getenv("EMAIL_SUBJECT_PREFIX", "Weekly Coaching Insights")

    # Find session JSON files (individual ones, not the combined file)
    session_files = [
        f for f in OUTPUT_DIR.glob("*_insights.json")
    ]

    # Also accept the combined file if individual ones aren't present
    if not session_files:
        combined = OUTPUT_DIR / f"{week_tag}_all_sessions.json"
        if combined.exists():
            session_files = [combined]

    if not session_files:
        sys.exit(
            "No session insight files found in ./output/\n"
            "Run  python process_transcripts.py  first."
        )

    print(f"\nLoading {len(session_files)} session file(s)...")
    aggregated, session_count = aggregate_sessions(session_files)

    print(f"Synthesizing insights from {session_count} session(s) with Claude...")
    email_text = synthesize_with_claude(client, aggregated, session_count)

    # Append coach name
    email_text += f"\n\n— {coach_name}"

    # Save plain text
    txt_path = WEEKLY_DIR / f"{week_tag}_email.txt"
    txt_path.write_text(email_text, encoding="utf-8")

    # Save HTML
    html_content = text_to_simple_html(email_text)
    html_path = WEEKLY_DIR / f"{week_tag}_email.html"
    html_path.write_text(html_content, encoding="utf-8")

    # Save a quick-review summary
    summary = {
        "week": week_tag,
        "sessions_processed": session_count,
        "top_topics": list(set(aggregated["main_topics"]))[:10],
        "top_emotional_themes": list(set(aggregated["emotional_themes"]))[:8],
        "all_action_items": list(set(aggregated["action_items"])),
    }
    summary_path = WEEKLY_DIR / f"{week_tag}_review_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    print(f"\n{'='*60}")
    print(f"  Weekly email generated for {coach_name}")
    print(f"  Sessions synthesized: {session_count}")
    print(f"{'='*60}")
    print(f"  Plain text : {txt_path}")
    print(f"  HTML email : {html_path}")
    print(f"  Review doc : {summary_path}")
    print(f"{'='*60}\n")
    print("EMAIL PREVIEW:")
    print("-" * 60)
    print(email_text[:1200] + ("..." if len(email_text) > 1200 else ""))


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Generate weekly coaching insights email.")
    parser.add_argument(
        "--week",
        help="Week label matching what was used in process_transcripts.py (e.g. 2026-W13).",
        default=None,
    )
    args = parser.parse_args()

    generate_weekly_email(week_label=args.week)
