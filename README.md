# Coaching Transcript Weekly Workflow

Automates the pipeline from raw session transcripts → weekly insights email.

## How It Works

```
transcripts/*.txt   →   process_transcripts.py   →   output/*_insights.json
                                                           ↓
                                              generate_weekly_email.py
                                                           ↓
                                         output/weekly/<week>_email.txt  (.html)
```

## Setup (one-time)

```bash
pip install -r requirements.txt
cp .env.example .env
# Edit .env and add your ANTHROPIC_API_KEY
```

Get your API key at: https://console.anthropic.com

## Weekly Workflow

### Step 1 — Drop transcripts in the folder

Add all your session transcripts to the `transcripts/` folder as `.txt` or `.md` files.
Name them however you like (e.g., `john_doe_mar27.txt`, `session_042.txt`).

### Step 2 — Extract per-session insights

```bash
python process_transcripts.py
```

This reads every file in `transcripts/`, calls Claude to extract:
- Main topics discussed
- Key takeaways
- Analogies / stories used
- Action items committed to
- Emotional themes / breakthroughs
- Notable quotes

Results saved to `output/<filename>_insights.json`.

### Step 3 — Generate the weekly email

```bash
python generate_weekly_email.py
```

Claude synthesizes across all sessions to find:
- Top recurring themes (seen across multiple clients)
- The single best analogy of the week
- Universal action items all clients can benefit from

**Output files:**

| File | Use |
|------|-----|
| `output/weekly/<week>_email.txt` | Copy-paste into Gmail / Mailchimp / ConvertKit |
| `output/weekly/<week>_email.html` | Use with HTML email senders |
| `output/weekly/<week>_review_summary.json` | Your personal review doc — raw theme list |

### Optional: specify the week label

```bash
python process_transcripts.py --week 2026-W13
python generate_weekly_email.py --week 2026-W13
```

Useful if you're processing sessions from a prior week.

## Folder Structure

```
coachingsessions/
├── transcripts/          ← Drop your .txt or .md transcripts here
├── output/
│   ├── *_insights.json   ← Per-session extractions
│   └── weekly/
│       ├── *_email.txt   ← Ready-to-send plain text email
│       ├── *_email.html  ← HTML version
│       └── *_review_summary.json  ← Your weekly review doc
├── process_transcripts.py
├── generate_weekly_email.py
├── requirements.txt
└── .env                  ← Your API key (never commit this)
```

## Tips

- **30-50 sessions/week:** The workflow handles any volume. More sessions = richer synthesis.
- **Transcript format:** Paste raw text from Zoom, Otter.ai, Rev, or any transcription tool.
- **Clean up between weeks:** After generating the email, move processed transcripts to an archive folder so next week starts fresh.
- **Customize tone:** Edit the prompts in `generate_weekly_email.py` (the `SYNTHESIS_PROMPT` variable) to match your voice.
