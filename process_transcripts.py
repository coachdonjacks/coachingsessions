#!/usr/bin/env python3
"""
process_transcripts.py

Step 1 of the coaching workflow:
  - Reads every transcript file in the ./transcripts/ folder
  - Uses Claude to extract per-session insights (topics, takeaways, analogies, action items)
  - Saves a structured JSON summary for each session in ./output/

Supported transcript formats: .txt, .md
"""

import json
import os
import sys
from datetime import date
from pathlib import Path

import anthropic
from dotenv import load_dotenv

load_dotenv()

TRANSCRIPTS_DIR = Path("transcripts")
OUTPUT_DIR = Path("output")
OUTPUT_DIR.mkdir(exist_ok=True)

EXTRACTION_PROMPT = """You are analyzing a coaching session transcript. Extract the following in JSON format:

{
  "main_topics": ["list of 3-6 primary topics discussed"],
  "key_takeaways": ["list of 3-6 concrete insights or lessons from this session"],
  "analogies_used": ["any metaphors, stories, or analogies the coach used to illustrate a point"],
  "action_items": ["specific actions the client committed to or was encouraged to take"],
  "emotional_themes": ["recurring emotional patterns, fears, or breakthroughs observed"],
  "notable_quotes": ["1-3 powerful or memorable statements from the session (paraphrase ok)"]
}

Be concise and specific. Extract only what is genuinely present in the transcript.
If a category has nothing relevant, return an empty list.

TRANSCRIPT:
{transcript}
"""


def extract_insights(client: anthropic.Anthropic, transcript_text: str, filename: str) -> dict:
    """Call Claude to extract structured insights from a single transcript."""
    print(f"  Extracting insights from: {filename}")

    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1500,
        messages=[
            {
                "role": "user",
                "content": EXTRACTION_PROMPT.format(transcript=transcript_text[:40000]),  # ~30k words max
            }
        ],
    )

    raw = message.content[0].text.strip()

    # Strip markdown code fences if Claude wrapped the JSON
    if raw.startswith("```"):
        lines = raw.split("\n")
        raw = "\n".join(lines[1:-1]) if lines[-1] == "```" else "\n".join(lines[1:])

    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        print(f"  WARNING: Could not parse JSON for {filename}. Storing raw text.")
        return {"raw_extraction": raw}


def load_transcript(path: Path) -> str:
    """Read transcript file content."""
    return path.read_text(encoding="utf-8", errors="replace")


def process_all_transcripts(week_label: str | None = None) -> list[dict]:
    """Process all transcripts and return a list of per-session results."""
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        sys.exit("ERROR: ANTHROPIC_API_KEY not set. Copy .env.example to .env and add your key.")

    client = anthropic.Anthropic(api_key=api_key)

    transcript_files = sorted(
        [f for f in TRANSCRIPTS_DIR.iterdir() if f.suffix.lower() in {".txt", ".md"}]
    )

    if not transcript_files:
        sys.exit(
            f"No transcript files found in ./{TRANSCRIPTS_DIR}/\n"
            "Add .txt or .md transcript files and run again."
        )

    print(f"\nFound {len(transcript_files)} transcript(s). Processing...\n")

    results = []
    for path in transcript_files:
        transcript_text = load_transcript(path)
        if len(transcript_text.strip()) < 50:
            print(f"  Skipping {path.name} (too short / empty)")
            continue

        insights = extract_insights(client, transcript_text, path.name)
        session_data = {
            "filename": path.name,
            "processed_date": date.today().isoformat(),
            "week": week_label or date.today().strftime("%Y-W%W"),
            **insights,
        }
        results.append(session_data)

        # Save individual session output
        out_path = OUTPUT_DIR / f"{path.stem}_insights.json"
        out_path.write_text(json.dumps(session_data, indent=2), encoding="utf-8")
        print(f"  Saved: {out_path}")

    # Save combined week file
    week_tag = week_label or date.today().strftime("%Y-W%W")
    combined_path = OUTPUT_DIR / f"{week_tag}_all_sessions.json"
    combined_path.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(f"\nAll sessions saved to: {combined_path}")

    return results


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Extract insights from coaching transcripts.")
    parser.add_argument(
        "--week",
        help="Week label for output files (e.g. 2026-W13). Defaults to current week.",
        default=None,
    )
    args = parser.parse_args()

    sessions = process_all_transcripts(week_label=args.week)
    print(f"\nDone. Processed {len(sessions)} session(s).")
    print("Next step: run  python generate_weekly_email.py  to create your weekly email.")
