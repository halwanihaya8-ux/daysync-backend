"""
Parses Health Auto Export REST API payloads.

Real format: {"data": {"metrics": [{"name": str, "units": str, "data": [...]}]}}.

We bucket every data point by its YYYY-MM-DD date and aggregate to a single
daily value per metric (sum for steps and sleep, mean for HRV and HR).
"""
import logging
from collections import defaultdict
from datetime import datetime, date as date_cls

# Health Auto Export metric name -> our internal canonical metric
METRIC_MAP = {
    'heart_rate_variability': 'hrv',
    'hrv': 'hrv',
    'heart_rate': 'hr',
    'resting_heart_rate': 'resting_hr',  # stored separately as fallback for hr
    'step_count': 'steps',
    'steps': 'steps',
    'sleep_analysis': 'sleep',
}

# How to combine multiple intra-day samples into one daily value.
AGGREGATOR = {
    'hrv': 'mean',
    'hr': 'mean',
    'resting_hr': 'mean',
    'steps': 'sum',
    'sleep': 'sum',
}

def _parse_date(date_str):
    """Health Auto Export uses 'yyyy-MM-dd HH:mm:ss Z' or 'yyyy-MM-dd'."""
    if not date_str:
        return None
    s = str(date_str).strip()
    # Try several known shapes
    fmts = ['%Y-%m-%d %H:%M:%S %z', '%Y-%m-%d %H:%M:%S', '%Y-%m-%d', '%Y-%m-%dT%H:%M:%S%z', '%Y-%m-%dT%H:%M:%SZ']
    for fmt in fmts:
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    # Last resort: split on space or 'T' and try just the date piece
    head = s.split('T')[0].split(' ')[0]
    try:
        return date_cls.fromisoformat(head)
    except ValueError:
        return None

def _extract_value(metric, point):
    """Pick the right field from a Health Auto Export data point."""
    if metric == 'hr':
        # heart_rate uses {Min, Avg, Max}; we want the daily AVG
        for key in ('Avg', 'avg', 'qty'):
            if key in point and point[key] is not None:
                return float(point[key])
        return None
    if metric == 'sleep':
        # Aggregated: totalSleep | asleep. Unaggregated: qty (hours of that segment).
        for key in ('totalSleep', 'asleep', 'qty'):
            if key in point and point[key] is not None:
                return float(point[key])
        return None
    # hrv, steps, resting_hr -> qty
    if 'qty' in point and point['qty'] is not None:
        return float(point['qty'])
    return None

def parse_payload(payload):
    """
    Returns a list of dicts: {metric, date, value, sample_count, source}.

    Drops malformed points silently and logs a warning.
    """
    if not isinstance(payload, dict):
        return []
    data_obj = payload.get('data') or payload  # tolerate missing wrapper
    metrics = data_obj.get('metrics') if isinstance(data_obj, dict) else None
    if not isinstance(metrics, list):
        return []

    # Bucket: (metric, date) -> list[float]
    buckets = defaultdict(list)
    sources = {}

    for entry in metrics:
        if not isinstance(entry, dict):
            continue
        raw_name = str(entry.get('name', '')).strip().lower()
        canonical = METRIC_MAP.get(raw_name)
        if not canonical:
            continue
        for point in entry.get('data', []) or []:
            if not isinstance(point, dict):
                continue
            day = _parse_date(point.get('date') or point.get('startDate') or point.get('sleepStart'))
            value = _extract_value(canonical, point)
            if day is None or value is None:
                continue
            buckets[(canonical, day)].append(value)
            if 'source' in point and point['source']:
                sources[(canonical, day)] = str(point['source'])

    result = []
    for (metric, day), values in buckets.items():
        if not values:
            continue
        agg = AGGREGATOR.get(metric, 'mean')
        if agg == 'sum':
            v = float(sum(values))
        else:
            v = float(sum(values) / len(values))
        result.append({
            'metric': metric,
            'date': day,
            'value': v,
            'sample_count': len(values),
            'source': sources.get((metric, day)),
        })
    return result

def upsert_samples(db, user_id: str, samples: list[dict]) -> int:
    """Idempotent upsert of (user, metric, date) rows. Returns count written."""
    from models import HealthSample  # local import to avoid circular
    written = 0
    for s in samples:
        existing = (
            db.query(HealthSample)
            .filter(
                HealthSample.user_id == user_id,
                HealthSample.metric == s['metric'],
                HealthSample.date == s['date'],
            )
            .first()
        )
        if existing:
            existing.value = s['value']
            existing.sample_count = s['sample_count']
            if s.get('source'):
                existing.source = s['source']
        else:
            db.add(HealthSample(
                user_id=user_id,
                metric=s['metric'],
                date=s['date'],
                value=s['value'],
                sample_count=s['sample_count'],
                source=s.get('source'),
            ))
        written += 1
    try:
        db.commit()
    except Exception as exc:
        logging.exception('Health sample upsert failed: %s', exc)
        db.rollback()
        return 0
    return written
