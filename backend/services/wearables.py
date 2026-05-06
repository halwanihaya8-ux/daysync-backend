"""
Builds the 14-day input arrays the ML service expects (oldest -> newest).

Source of truth: the health_samples table, populated by the
/health/webhook/{token} endpoint that Health Auto Export posts to.

If a user has no samples yet, returns the canonical mock arrays so /dev/simulate
keeps working without external dependencies.
"""
import logging
from datetime import date, timedelta

WINDOW_DAYS = 14

MOCK_DATA = {
    'hrv_rmssd_ms':         [44, 46, 43, 48, 45, 47, 44, 50, 46, 43, 48, 45, 47, 44],
    'avg_hr_day_bpm':       [62, 64, 61, 60, 63, 62, 64, 60, 61, 63, 62, 64, 61, 60],
    'sleep_duration_hours': [7.5, 6.8, 8.0, 7.2, 7.0, 7.8, 6.5, 8.2, 7.1, 6.9, 7.6, 7.3, 7.0, 7.5],
    'steps':                [8200, 9100, 7500, 10200, 8800, 9500, 7800, 11000, 8600, 9200, 8400, 9800, 8100, 9000],
}

DEFAULTS = {'hrv': 45.0, 'hr': 62.0, 'resting_hr': 60.0, 'sleep': 7.0, 'steps': 8000.0}

def forward_fill(values, default):
    out = []
    last = default
    for v in values:
        if v is None:
            out.append(last)
        else:
            last = float(v)
            out.append(float(v))
    return out

def _series_for_metric(db, user_id, metric, end_day, default):
    """Return a 14-element list for `metric` ending on `end_day`. Forward-filled."""
    from models import HealthSample
    start_day = end_day - timedelta(days=WINDOW_DAYS - 1)
    rows = (
        db.query(HealthSample)
        .filter(
            HealthSample.user_id == user_id,
            HealthSample.metric == metric,
            HealthSample.date >= start_day,
            HealthSample.date <= end_day,
        )
        .all()
    )
    by_date = {r.date: float(r.value) for r in rows}
    raw = []
    for i in range(WINDOW_DAYS):
        d = start_day + timedelta(days=i)
        raw.append(by_date.get(d))
    return forward_fill(raw, default)

def fetch_wearable_data(user, db=None):
    """
    Build the 4 arrays the ML service expects, from the health_samples table.

    `db` is required when reading real data; if None or the user has no samples,
    falls back to the canonical mock arrays (keeps /dev/simulate keyless).
    """
    if db is None:
        return MOCK_DATA.copy()
    try:
        from models import HealthSample
        has_any = db.query(HealthSample).filter(HealthSample.user_id == user.id).first()
        if not has_any:
            return MOCK_DATA.copy()
        end_day = date.today()
        hrv = _series_for_metric(db, user.id, 'hrv', end_day, DEFAULTS['hrv'])
        # Prefer avg HR; if the user only sent resting_hr, use that.
        hr_rows = db.query(HealthSample).filter(HealthSample.user_id == user.id, HealthSample.metric == 'hr').first()
        hr_metric = 'hr' if hr_rows else 'resting_hr'
        hr_default = DEFAULTS['hr'] if hr_metric == 'hr' else DEFAULTS['resting_hr']
        hr = _series_for_metric(db, user.id, hr_metric, end_day, hr_default)
        sleep = _series_for_metric(db, user.id, 'sleep', end_day, DEFAULTS['sleep'])
        steps = _series_for_metric(db, user.id, 'steps', end_day, DEFAULTS['steps'])
        return {
            'hrv_rmssd_ms': hrv,
            'avg_hr_day_bpm': hr,
            'sleep_duration_hours': sleep,
            'steps': steps,
        }
    except Exception as exc:
        logging.exception('fetch_wearable_data fell back to mock: %s', exc)
        return MOCK_DATA.copy()

def build_webhook_url(base_url: str, token: str) -> str:
    """Helper for /health/webhook-url. base_url has no trailing slash."""
    base = (base_url or '').rstrip('/')
    return f'{base}/health/webhook/{token}'
