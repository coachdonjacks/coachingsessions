# Coaching Transcript Weekly Workflow

Automates the full pipeline: pulls transcripts from Zoom → extracts insights → generates weekly email.

## How It Works

```
Zoom Cloud Recordings
        ↓
fetch_zoom_transcripts.py  →  transcripts/*.txt
        ↓
process_transcripts.py     →  output/*_insights.json
        ↓
generate_weekly_email.py   →  output/weekly/<week>_email.txt (.html)
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

### 3. Create a Zoom Server-to-Server OAuth app

1. Go to https://marketplace.zoom.us → **Develop** → **Build App**
2. Choose **Server-to-Server OAuth**
3. Name it (e.g., "Coaching Transcript Fetcher") and create it
4. Under **Scopes**, add: `recording:read:admin`
5. **Activate** the app
6. Copy **Account ID**, **Client ID**, **Client Secret** into `.env`

Also make sure in your Zoom account settings (**Settings → Recording**):
- Cloud Recording is **enabled**
- **"Create audio transcript"** is checked under Advanced Cloud Recording settings

---

## Weekly Workflow (3 commands)

### Step 1 — Pull transcripts from Zoom

```bash
python fetch_zoom_transcripts.py
```

Fetches all cloud recordings from the **past 7 days**, downloads each transcript (VTT format), converts to clean plain text, and saves to `transcripts/`.

```bash
# Custom date range:
python fetch_zoom_transcripts.py --from 2026-03-17 --to 2026-03-24

# Custom lookback window:
python fetch_zoom_transcripts.py --days 14
```

Already-downloaded transcripts are skipped automatically (safe to re-run).

### Step 2 — Extract per-session insights

```bash
python process_transcripts.py
```

Claude reads each transcript and extracts:
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
├── fetch_zoom_transcripts.py  ← Step 1: pull from Zoom
├── process_transcripts.py     ← Step 2: extract insights per session
├── generate_weekly_email.py   ← Step 3: synthesize + write email
├── transcripts/               ← Auto-populated from Zoom (or drop files manually)
├── output/
│   ├── *_insights.json        ← Per-session extractions
│   └── weekly/
│       ├── *_email.txt        ← Ready-to-send plain text email
│       ├── *_email.html       ← HTML version
│       └── *_review_summary.json
├── requirements.txt
├── .env.example
└── .env                       ← Your keys (never committed)
```

---

## Tips

- **30-50 sessions/week:** The workflow handles any volume. More sessions = richer synthesis.
- **Clean up between weeks:** After generating the email, either delete or archive the `transcripts/` files so next week starts fresh.
- **Manually add transcripts:** If a session wasn't recorded in Zoom, just drop a `.txt` file in `transcripts/` and it'll be included automatically.
- **Customize tone:** Edit `SYNTHESIS_PROMPT` in `generate_weekly_email.py` to match your voice.
- **Coach name in email:** Set `COACH_NAME` in `.env` — it's auto-appended to every email.
