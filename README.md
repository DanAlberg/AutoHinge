# AutoHinge

End-to-end Hinge profile scanner + scorer + opener selector for Android via ADB.

## What it does

- Connects to an Android device (ADB)
- Scans a single profile with UI XML + photo crops
- Extracts core biometrics from the UI
- Runs a multi-stage LLM pipeline for visual analysis, profile evaluation, scoring, and message generation
- Taps the chosen target like, enters a comment, and sends a priority like
- On reject, taps the skip/dislike button

## The Pipeline

The system uses a 6-stage LLM pipeline with intermediate scoring and gate decisions:

```
┌─────────────────────────────────────────────────────────────────┐
│  PROFILE SCAN                                                    │
│  UI XML parsing + photo cropping                                 │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│  LLM1: Visual Analysis                                           │
│  Photo descriptions + visual trait inference                     │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│  LLM2: Profile Enrichment                                        │
│  Job tier (T0-T4), elite university detection, home country      │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│  SCORING                                                         │
│  Dual scores: Long-term compatibility + Short-term compatibility │
│  Thresholds: T_LONG=15, T_SHORT=20, dominance margin=10          │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│  GATE DECISION                                                   │
│  reject | long_pickup | short_pickup                             │
│  (based on scores + dating intentions)                           │
└─────────────────────────────────────────────────────────────────┘
                              ↓
         ┌────────────────────┴────────────────────┐
         ↓                                          ↓
┌─────────────────────┐                  ┌─────────────────────┐
│  REJECT PATH        │                  │  PICKUP PATH        │
│  LLM5 safety check  │                  │  LLM3: 5 openers    │
│  → dislike tap      │                  │  LLM3.5: critique   │
└─────────────────────┘                  │  LLM4: rewrite      │
                                         │  LLM4.5: pick/fail  │
                                         │  LLM5: safety check │
                                         │  → send message     │
                                         └─────────────────────┘
```

**LLM Stages:**
- **LLM1**: Visual analysis of photos (descriptions, attractiveness tier, visual traits)
- **LLM2**: Enrichment (job tier classification, elite university detection, home country resolution)
- **LLM3**: Generate 5 candidate openers (long or short variant based on gate decision)
- **LLM3.5**: Agentic critique of all openers from a critical perspective
- **LLM4**: Rewrite all 5 lines incorporating critique feedback
- **LLM4.5**: Final selection — pick the best opener or fail all if none meet quality bar
- **LLM5**: Safety check (validates messages before sending, prevents unfair rejections, detects elite profiles for manual review)

## Scoring System

Two parallel scoring systems:

**Long Score** — Optimized for long-term relationship potential
- Weights: Dating intentions, age, job tier, university, lifestyle factors
- Hard kills: Smoking, drugs, certain visual red flags

**Short Score** — Optimized for short-term compatibility  
- Weights: Dating intentions, playfulness signals, visual appeal
- Different threshold and weighting priorities

**Gate Logic:**
- Both below threshold → reject
- Long dominant (≥10 margin above threshold) → long_pickup
- Short dominant (≥10 margin above threshold) → short_pickup
- Dating intentions can override (e.g., "Life partner" seeking + short_pickup → reject/long)

## Requirements

- Android device with USB debugging enabled and Hinge installed
- adb on PATH
- Python 3.12+
- uv (optional but recommended)

## Setup

1) Create `app/.env`:
   ```
   OPENAI_API_KEY=your-key
   GEMINI_API_KEY=your-key
   LLM_PROVIDER=gemini|openai
   GEMINI_MODEL=gemini-2.5-pro
   GEMINI_SMALL_MODEL=gemini-2.5-flash
   OPENAI_MODEL=gpt-4o
   OPENAI_SMALL_MODEL=gpt-4o-mini
   # Optional: copy profiles.db to this folder after each run
   HINGE_DB_BACKUP_DIR=C:\Users\you\backup-folder
   ```
   Only the key for your provider is required. `LLM_PROVIDER` defaults to gemini if unset.

2) Install dependencies:
   ```bash
   cd app
   uv sync
   ```

## Run

```bash
cd app
uv run python start.py
```

## Interactive Pause Menu

Press `Ctrl+C` during execution to access the pause menu:
1. Continue (Resume program)
2. Toggle Unrestricted Mode
3. Toggle Elite Review Mode
4. Undo / Retry (restart decision & action for current profile)
5. Quit

## Options

- `--unrestricted`: Skip confirmations before dislike and send priority like (fully autonomous mode)
- `--no-review-elite`: Disable manual review for elite profiles (enabled by default)
- `--profiles N`: Process N profiles then exit (default: 1)
- `--verbose`: Enable verbose console logs (includes `[SCROLL]` and `[PHOTO]`)

**Elite Review Mode** — When enabled (default), LLM5 flags profiles with T3/T4 job bands or elite university + high-trajectory career for manual review instead of auto-action.

## Log a Match

```bash
cd app
uv run python log_match.py
```

Workflow:
- Enter a name (partial ok), optionally age/height
- Pick the correct liked profile from the list
- Enter match time (supports formats like `2026-01-25 16:49` or `25 Jan 16:49`)
- The script updates `profiles.db` with `matched=1` and `match_time`

## Outputs

- `profiles.db` at repo root (created on first successful insert)
- `app/images/crops/` — photo crops
- `app/logs/` — run JSON + score table
- Optional AI trace: set `HINGE_AI_TRACE_FILE=app/logs/ai_trace_YYYYMMDD_HHMMSS.log`
- Optional run JSON echo: set `HINGE_SHOW_RUN_JSON=1`

## Architecture

```
app/
├── start.py          # Entry point, main pipeline orchestration
├── extraction.py     # Profile extraction, LLM1/LLM2 calls
├── scoring.py        # Long/short scoring logic
├── openers.py        # LLM3-LLM4.5 message generation
├── prompts.py        # All LLM prompt templates
├── llm_client.py     # LLM API client (Gemini/OpenAI)
├── ui_scan.py        # ADB UI scanning, photo cropping
├── sqlite_store.py   # Profile database operations
└── log_match.py      # Match logging utility