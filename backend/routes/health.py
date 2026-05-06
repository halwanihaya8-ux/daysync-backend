import logging
import os
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from auth import get_current_user
from database import get_db
from models import HealthSample, User
from services.health_auto_export import parse_payload, upsert_samples
from services.wearables import build_webhook_url

router = APIRouter()

@router.post('/health/webhook/{token}')
async def health_webhook(token: str, request: Request, db: Session = Depends(get_db)):
    """
    Receives Apple Health data forwarded by the Health Auto Export iOS app.

    No JWT — the per-user webhook token IS the credential. Treat it as a secret.
    Body is the raw Health Auto Export JSON payload.
    """
    user = db.query(User).filter(User.webhook_token == token).first()
    if not user:
        raise HTTPException(status_code=404, detail='Unknown webhook token')
    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail='Body must be JSON')
    try:
        samples = parse_payload(payload)
    except Exception as exc:
        logging.exception('Webhook parse failed: %s', exc)
        raise HTTPException(status_code=400, detail='Could not parse Health Auto Export payload')
    written = upsert_samples(db, user.id, samples)
    return {'received': len(samples), 'stored': written, 'user_id': user.id}

@router.get('/health/webhook-url')
def webhook_url(user: User = Depends(get_current_user)):
    """
    Returns the user's personal webhook URL to paste into Health Auto Export
    (Automation -> REST API -> URL).
    Set PUBLIC_BASE_URL in env to your reachable host (e.g. an ngrok or render URL).
    """
    base = os.getenv('PUBLIC_BASE_URL', 'http://localhost:8000')
    return {
        'url': build_webhook_url(base, user.webhook_token),
        'token': user.webhook_token,
        'method': 'POST',
        'content_type': 'application/json',
        'note': 'Paste this URL into Health Auto Export -> Automations -> REST API.',
    }

@router.post('/health/webhook-url/rotate')
def rotate_webhook_token(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Rotate the webhook token (e.g. if the user thinks the URL leaked)."""
    import uuid
    user.webhook_token = str(uuid.uuid4())
    db.commit(); db.refresh(user)
    base = os.getenv('PUBLIC_BASE_URL', 'http://localhost:8000')
    return {'url': build_webhook_url(base, user.webhook_token), 'token': user.webhook_token}

@router.get('/health/samples/recent')
def recent_samples(days: int = 14, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Diagnostic: list the most recent ingested samples for this user."""
    from datetime import date, timedelta
    cutoff = date.today() - timedelta(days=max(1, min(days, 90)))
    rows = (
        db.query(HealthSample)
        .filter(HealthSample.user_id == user.id, HealthSample.date >= cutoff)
        .order_by(HealthSample.date.desc(), HealthSample.metric)
        .all()
    )
    return [
        {'metric': r.metric, 'date': r.date.isoformat(), 'value': r.value, 'sample_count': r.sample_count, 'source': r.source}
        for r in rows
    ]
