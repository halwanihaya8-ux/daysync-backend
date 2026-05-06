# DaySync AI MVP — Changes from previous build

Two rounds of changes. Round 1 = spec compliance fixes. Round 2 = swap Open Wearables for Health Auto Export (Apple Health → webhook).

---

## Recovery model — what it actually takes

The Flask ML service at `/api/predict` requires exactly **4 lists**, each ≥5 daily values, oldest first:

| Field | Meaning | Apple Health source |
|---|---|---|
| `hrv_rmssd_ms` | HRV in ms (model trained as RMSSD; Apple gives SDNN — same field used) | `HeartRateVariabilitySDNN` |
| `avg_hr_day_bpm` | **Average daily heart rate**, not resting | aggregate of `HeartRate` samples |
| `sleep_duration_hours` | Sleep in hours | `SleepAnalysis` (totalSleep) |
| `steps` | Daily step count | `StepCount` (sum) |

The model engineers 7 features per day (z-scores vs 14-day baseline, EWM strain, sleep debt, HRV trend, recovery ratio = HRV / (avg_HR + 1)) and a 5-day window → flat 35-element vector → SHAP-selected 25 features → XGBoost. The `recovery_ratio` feature is the most important predictor, followed by HRV z-scores. Resting HR would shift the recovery_ratio distribution out of training range, which is why we feed avg HR.

---

## Round 2 — Open Wearables → Health Auto Export

### What replaced what
- **Removed:** `services/wearables.py` Open Wearables HTTP calls, `mirror_user`, `connect_url`, `/wearables/connect` endpoint, `OPENWEARABLES_URL`/`OPENWEARABLES_TOKEN` env vars, `users.ow_user_id` column.
- **Added:** webhook ingestion endpoint, parser for the real Health Auto Export JSON format, `health_samples` table, per-user webhook tokens, `PUBLIC_BASE_URL` env var.

### New DB table — `health_samples`
One row per `(user_id, metric, date)` (unique constraint, idempotent upsert). Stores HRV / HR / resting_hr / sleep / steps as one daily aggregate.

### New service — `services/health_auto_export.py`
- `parse_payload(payload)` — handles the real Health Auto Export shape: `data.metrics[].{name, units, data[]}` with metric-specific fields:
  - `heart_rate_variability` → uses `qty` → bucket: `hrv` (mean of intra-day samples)
  - `heart_rate` → uses `Avg` (capital A, per HAE wiki) → bucket: `hr` (mean)
  - `resting_heart_rate` → uses `qty` → bucket: `resting_hr` (mean) — fallback only
  - `step_count` → uses `qty` → bucket: `steps` (sum)
  - `sleep_analysis` → uses `totalSleep` then `asleep` then `qty` → bucket: `sleep` (sum, handles aggregated and unaggregated formats)
- Buckets multiple intra-day samples into one daily value, drops malformed entries silently, tolerates missing date wrapper.
- `upsert_samples(db, user_id, samples)` — idempotent, safe to retry the same payload.

### Rewritten — `services/wearables.py`
- `fetch_wearable_data(user, db)` — now reads the last 14 days from `health_samples`, prefers avg HR (`hr` metric) but falls back to resting HR if that's all the user has, forward-fills nulls, returns the same dict shape the ML service expects.
- Mock 14-day arrays kept as fallback when the user has no samples yet → keeps `/dev/simulate` working without any external service.

### New endpoints — `routes/health.py`
| Method | Path | Auth | Purpose |
|---|---|---|---|
| `POST` | `/health/webhook/{token}` | none (token IS auth) | Receives Health Auto Export payloads, parses, upserts |
| `GET` | `/health/webhook-url` | JWT | Returns the user's full webhook URL to paste into HAE |
| `POST` | `/health/webhook-url/rotate` | JWT | Generates a fresh token if the URL leaked |
| `GET` | `/health/samples/recent?days=14` | JWT | Diagnostic — list ingested samples |

### `users` table changes
- Removed: `ow_user_id`
- Added: `webhook_token` (unique uuid generated at register, returned on register and login)

### App Inventor guide — Screen 5
New screen added to walk the user through installing Health Auto Export on their iPhone, granting Apple Health permissions for the four required metrics, pasting the webhook URL into the app's REST API automation, and seeding 14 days of history with a manual export.

### `.env.example`
- Removed: `OPENWEARABLES_URL`, `OPENWEARABLES_TOKEN`
- Added: `PUBLIC_BASE_URL` (your reachable host — ngrok, Render, Fly, Railway, etc. — used in the webhook URL handed to the iPhone)

### What the user does once per device
1. Register / log in (webhook token issued automatically)
2. Open Screen 5, copy the webhook URL
3. Install Health Auto Export from the App Store, grant Apple Health permissions
4. Automations → New → REST API → paste URL, POST, JSON, hourly schedule
5. Manual Export once to seed last 14 days
6. From there it runs in the background; the 6:00 AM job builds today's recovery from the latest 14 days of `health_samples`

### Validations
- Verified Health Auto Export's actual JSON format against the official wiki at `github.com/Lybron/health-auto-export/wiki/API-Export---JSON-Format`. ChatGPT's example payload (`{"type":"heart_rate","value":72}`) was wrong — the real format wraps everything in `data.metrics[]` with shape-specific fields per metric.
- Parser tested against a realistic multi-metric, multi-sample payload covering all 5 input types plus malformed entries — averages, sums, and date parsing all behave correctly.
- All 21 routes compile and register without import errors.
- No Open Wearables references remain anywhere in code, env, or docs.

---

## Round 1 — Spec compliance fixes (carried forward)

### 1. `docker-compose.yml` — `.env` not `.env.example`
Previous: `env_file: - .env.example`. Real keys placed in `.env` were silently ignored.
Now: `env_file: - .env`. Workflow: `cp .env.example .env`, fill in keys, `docker compose up --build`.

### 2. Morning summary push notification
Previous: generic `'Good morning! Your DaySync schedule is ready.'`
Now: `'Good morning! Recovery: {zone}. First task: {task} at {HH:MM}'` per spec.

### 3. Per-task "leave for X" notifications
Previously missing entirely. Now `daily_recovery_job` calls `schedule_leave_notifications()` after each rebuild, which registers an APScheduler `DateTrigger` per TRAVEL block at `task_start - travel - prep`. Past times are skipped, IDs keyed `leave_{user_id}_{item_id}` with `replace_existing=True`.

### 4 & 5. Removed `__import__('datetime')` workarounds
In `routes/goals.py` (the `date` query param shadowed the imported class — fixed with `Query(alias='date')`) and in `scheduler_jobs.py` (now imports `time` at the top).

---

## Verified untouched / still correct
- DB schema for routines, goals, recovery_logs, schedule_logs, schedule_items
- OR-Tools CP-SAT scheduler: 06:00–22:45 horizon, 68 × 15-min slots, PREP→TRAVEL→GOAL ordering, 5s solver limit, infeasibility falls back to routines-only
- Readiness mapping: optimal→HIGH (all goals), normal→MEDIUM (1 highest-priority), fatigued→LOW (0 goals)
- ML service code and model artifacts unchanged
- Maps fallback (20 min default), OpenAI parser fallback, JWT auth, CORS, all flat-JSON response shapes for App Inventor
- `/dev/simulate` still keyless (uses mock fallback)

## How to run
```
cp .env.example .env
# Fill in OPENAI_API_KEY, GOOGLE_MAPS_API_KEY, JWT_SECRET, PUBLIC_BASE_URL.
# Or leave them as placeholders — /dev/simulate works without them.
docker compose up --build
```

For the Health Auto Export side, `PUBLIC_BASE_URL` must be reachable from an iPhone — use ngrok, Cloudflare Tunnel, or deploy the API to Render / Fly / Railway.
