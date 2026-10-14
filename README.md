# Database Query Agent

Natural-language CCTV database query agent for the Cynapse take-home assignment.

## Overview

This project translates free-form user requests into database queries over CCTV frame records. It includes:

- prompt guardrails with a deterministic first pass and an OpenAI judge layer
- structured prompt parsing
- SQL planning
- query execution
- session-scoped follow-up handling

The design write-up and implementation notes live in [writeup.md](writeup.md).

## Requirements

- Python 3.11 or newer
- An OpenAI API key

## Setup

1. Create and activate a virtual environment:

   ```powershell
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1
   ```

2. Install dependencies:

   ```powershell
   pip install -r requirements.txt
   ```

3. Configure your API key in `.env.local`:

   ```env
   OPENAI_API_KEY=your_api_key_here
   ```

   The guardrail judge, parser, and SQL planner all load credentials from `.env.local`.

## Running

Start the interactive agent:

```powershell
python -m pipeline
```

## Testing

Run the test suite with:

```powershell
pytest
```

## Project Structure

- `pipeline/` - application code
- `data/` - local SQLite database used by the agent
- `tests/` - automated tests
- `results/` - generated query outputs
- `writeup.md` - assignment write-up and evaluation discussion

## Notes

- The bundled SQLite database is `data/cctv_frames.db`.
- Query results are written to `results/result_*.json`.
