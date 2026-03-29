# Coaching Transcript Weekly Workflow

Pulls Zoom meeting summaries from your Gmail inbox, extracts insights across all sessions with Claude, and generates a ready-to-send weekly email.

## How It Works

```
Gmail inbox (Zoom summary emails)
        ↓
fetch_email_summaries.py  →  transcripts/*.txt
        ↓
process_transcripts.py    →  output/*_insights.json
        ↓
generate_weekly_email.py  →  output/weekly/<week>_email.txt (.html)
```

---

## One-Time Setup

### 1. Install dependencies

```bash
pip install -r requirements.txt
cp .env.example .env
```

### 2. Get your Anthropic API key

Add to `.env`:
```
ANTHROPIC_API_KEY=...
```
Get it at: https://console.anthropic.com

### 3. Enable Gmail IMAP + create an App Password

**Enable IMAP in Gmail:**
1. Open Gmail → Settings (gear icon) → **See all settings**
2. Go to **Forwarding and POP/IMAP** tab
3. Under IMAP Access → **Enable IMAP** → Save Changes

**Create an App Password:**
1. Go to myaccount.google.com → **Security**
2. Enable **2-Step Verification** if not already on
3. Go back to Security → **App passwords**
4. Create a new one — name it "Coaching Workflow"
5. Copy the 16-character password

Add both to `.env`:
```
GMAIL_ADDRESS=djacks@yourcoach.com
GMAIL_APP_PASSWORD=xxxx xxxx xxxx xxxx
```

That's the entire setup. No API approvals, no OAuth apps — just your email credentials.

---

## Weekly Workflow (3 commands)

### Step 1 — Pull Zoom summaries from Gmail

```bash
python fetch_email_summaries.py
```

Searches your inbox for all Zoom meeting summary emails from the **past 7 days**, extracts the text, and saves each one to `transcripts/`. Already-saved summaries are skipped automatically.

```bash
# Look back further:
python fetch_email_summaries.py --days 14
```

### Step 2 — Extract per-session insights

```bash
python process_transcripts.py
```

Claude reads each summary and extracts:
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

Claude synthesizes across all 30-50 sessions to find recurring patterns and produces a polished email with:
- Top themes seen across multiple clients
- Analogy of the week
- Universal action items for all readers

**Output files:**

| File | Use |
|------|-----|
| `output/weekly/<week>_email.txt` | Copy-paste into Gmail / Mailchimp / ConvertKit |
| `output/weekly/<week>_email.html` | HTML version for styled senders |
| `output/weekly/<week>_review_summary.json` | Your personal review doc — raw theme list |

---

## Folder Structure

```
coachingsessions/
├── fetch_email_summaries.py   ← Step 1: pull from Gmail
├── process_transcripts.py     ← Step 2: extract insights per session
├── generate_weekly_email.py   ← Step 3: synthesize + write email
├── transcripts/               ← Auto-populated from Gmail (or drop files manually)
├── output/
│   ├── *_insights.json        ← Per-session extractions
│   └── weekly/
│       ├── *_email.txt        ← Ready-to-send plain text email
│       ├── *_email.html       ← HTML version
│       └── *_review_summary.json
├── requirements.txt
├── .env.example
└── .env                       ← Your credentials (never committed)
```

---

## Tips

- **30-50 sessions/week:** The workflow handles any volume. More sessions = richer synthesis.
- **Manually add sessions:** If a session wasn't captured by Zoom AI, drop a `.txt` file in `transcripts/` and it'll be included automatically.
- **Clean up between weeks:** After generating the email, archive or delete the files in `transcripts/` so next week starts fresh.
- **Customize tone:** Edit `SYNTHESIS_PROMPT` in `generate_weekly_email.py` to match your voice.
- **Coach name in email:** Set `COACH_NAME` in `.env` — it's auto-appended to every email.
