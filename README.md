# swimops

A personal CLI for signing in to Garmin Connect and keeping original activity FIT files locally.

It uses [`garminconnect`](https://github.com/cyberjunky/python-garminconnect), an unofficial client for Garmin Connect web services, and Garmin's [official FIT SDK](https://github.com/garmin/fit-python-sdk).

## Requirements and installation

- [`uv`](https://docs.astral.sh/uv/)
- Python 3.12 or later (`uv` manages it when needed)

```bash
uv sync
```

## Usage

Sign in interactively:

```bash
uv run garmin login
```

The password and MFA code, when applicable, are neither displayed nor saved. Tokens are stored outside the repository at `~/.local/share/swimops/garmin/garmin_tokens.json` and reused in later runs.

List the ten most recent activities, or change the limit:

```bash
uv run garmin activities
uv run garmin activities --limit 25
```

Download and register all activities in an inclusive date range:

```bash
uv run garmin sync --since 2026-04-15
uv run garmin sync --since 2026-04-15 --until 2026-09-09
```

Without `--until`, the range ends on the current date. All sports are included. Original FIT files are stored under `data/fit/<year>/<month>/`, and the index is stored in `data/garmin.sqlite`. Pool sessions are processed automatically. Later runs skip complete activities and automatically repair a missing FIT file or database record.

The data directory can be changed independently of the dates and other options:

```bash
uv run garmin sync --since 2026-04-15 --data-dir /path/to/data
```

The final summary reports downloaded, existing, and failed activities. An individual failure does not stop the remaining downloads; a later run retries it. The command exits with a nonzero status when any activity fails.

Process previously downloaded pool swimming FIT files:

```bash
uv run garmin parse-swims
```

The command stores each session summary, laps, lengths, and time in heart-rate zones in SQLite. Average pace uses active swimming time; SWOLF is calculated for each length as seconds plus strokes. Zone indexes are preserved as found in the FIT file, including time below and above the five configured zones.

Processed sessions are skipped on later runs. To recalculate them after changing the parser:

```bash
uv run garmin parse-swims --force
```

## Athlete profile

Personal planning preferences live in `athlete.toml`, which is ignored by Git. Create it from the shared example:

```bash
cp athlete.example.toml athlete.toml
```

Supported fields are:

```toml
pool_length_m = 25
target_distance_m = 1500
swim_days_per_week = 3
available_equipment = [
  "paddles",
  "fins",
  "snorkel",
  "kickboard",
  "pull_buoy",
]
```

All fields are optional, but the agent must not invent missing values. `target_distance_m` is a planning target rather than a strict maximum, and `swim_days_per_week` describes availability rather than a required number of sessions.

At the first coaching or workout-planning interaction, the agent calls `get_athlete_profile`. If the profile is missing or incomplete, the tool reports `missing_fields`; the agent asks for those preferences together and saves the supplied answers with `update_athlete_profile`. This onboarding does not run for unrelated operations such as synchronization or factual history queries.

To keep the profile elsewhere, set `SWIMOPS_ATHLETE_CONFIG` to its path. This variable can be supplied by the shell, an ignored `.env` file loaded by the host, or the MCP host configuration.

Keep dynamic information out of the profile. Current fatigue, pain or injury, session-specific goals, and target pace should come from the current request or recorded history because they can become stale quickly.

## MCP

The local server runs over `stdio`:

```bash
uv run garmin-mcp
```

Generic configuration for an MCP host:

```json
{
  "mcpServers": {
    "swimops": {
      "command": "uv",
      "args": [
        "--directory",
        "/path/to/swimops",
        "run",
        "garmin-mcp"
      ],
      "env": {
        "GARMIN_DATA_DIR": "/path/to/swimops/data",
        "SWIMOPS_ATHLETE_CONFIG": "/path/to/swimops/athlete.toml"
      }
    }
  }
}
```

Replace the example paths with local absolute paths. The host starts the MCP server automatically; no separate process needs to remain open.

Besides query tools, the MCP server exposes `get_auth_status`, `get_athlete_profile`, `update_athlete_profile`, `sync_activities`, and `get_sync_status`. The profile tools return configured preferences, report missing fields, and save only user-provided values. `sync_activities` downloads the requested range and processes pool sessions. If a valid session is missing, it returns an instruction to run `uv run garmin login` locally; the MCP server never asks for a username, password, or MFA code.

## Reports

The local app reads the same SQLite database. It can filter sessions by date and workout, exclude warm-up and cool-down, and show volume, pace, SWOLF, strokes, and heart rate:

```bash
uv run streamlit run src/swimops/report_app.py
```

Open `http://localhost:8501`. The app does not modify data. The overview separates activity count, distance, and time by sport and colors weekly volume by activity. Pool details show progress without mixing in soccer or running. The comparison view overlays selected workouts and can switch among pace, SWOLF, strokes, heart rate, and distance.

It can also run in Docker while retaining data on the host and mounting it read-only:

```bash
docker compose up --build
```

## Workout proposals

A workout can be validated and reviewed locally before it is created in Garmin:

```bash
uv run garmin workout-preview examples/swim-workout.json
```

The format supports warm-up, swimming, rest, repetitions, cool-down, stroke, equipment, drills, notes, and one pace target per step. Supported equipment values are `paddles`, `fins`, `pull_buoy`, `kickboard`, and `snorkel`. Each proposal includes its pool length, and all distances must be multiples of that length.

The builder automatically adds an untimed rest between main steps so there is time to prepare or change equipment and continue with the Lap button. Rests inside repetitions or with a specific duration are declared explicitly with `duration_s`. A workout can disable automatic rests with `"auto_rest_between_steps": false`.

The MCP server also exposes `preview_swim_workout`. This tool only validates and presents the proposal; it neither contacts Garmin nor creates workouts.

Existing workouts can be queried without modifying them:

```bash
uv run garmin workouts
uv run garmin workout 1675490181
```

The MCP server provides the same queries through `list_workouts` and `get_workout`. Both tools read Garmin Connect using the saved local session.

After reviewing the preview, creation requires explicit confirmation:

```bash
uv run garmin workout-create examples/swim-workout.json --confirm
```

In MCP, `create_swim_workout` requires `confirmed=true`. Use it only after showing `preview_swim_workout` and receiving user approval. Creation saves the workout to Garmin Connect.

To select another token directory, always outside the repository:

```bash
GARMIN_TOKEN_DIR=/private/path/garmin uv run garmin login
```

The token directory is created with `0700` permissions; the library creates the token file with `0600` permissions. Treat it like a password. If the session becomes invalid, run `uv run garmin login` again.

## Agent integration and responsibilities

SwimOps separates coaching decisions from deterministic Garmin operations:

- The agent analyzes available history, chooses a training objective, prepares a workout proposal, explains it, and obtains explicit user confirmation.
- The MCP exposes local history, validates and previews workout proposals, converts them to Garmin's format, and uploads an explicitly confirmed workout.
- The local CLI handles interactive Garmin login and MFA. Neither the agent nor the MCP requests credentials.

Workout creation always follows this sequence:

```text
preview_swim_workout
→ show the preview
→ receive explicit user confirmation
→ create_swim_workout(confirmed=true)
```

Original FIT files are retained under `data/fit/` as the local historical source. SQLite stores the activity index and parsed or derived metrics used by reports and MCP queries. Derived information should remain reproducible from factual activity data whenever practical.

The MCP does not implement coaching policy. Decisions such as the next training focus, whether repeating a benchmark is useful, and how to interpret recent performance belong to the agent. Deterministic processing, schema validation, preview generation, and Garmin payload construction belong to SwimOps.

## Development

```bash
uv run pytest
```
