from datetime import date, datetime, time
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from auth import get_current_user
from database import get_db
from models import Goal, RecoveryLog, Routine, ScheduleItem, ScheduleLog, User
from services.openai_parser import parse_tasks
from services.recovery import call_ml_service
from services.scheduler import build_schedule, parse_hhmm
from services.wearables import fetch_wearable_data

router = APIRouter()

class ParseIn(BaseModel):
    text: str
    user_id: str | None = None

class RateIn(BaseModel):
    rating: int

class ItemPatch(BaseModel):
    start_time: str | None = None
    is_locked: bool | None = None

def item_out(i: ScheduleItem):
    return {
        'id': i.id,
        'task': i.task_name,
        'start': i.start_time.strftime('%H:%M'),
        'end': i.end_time.strftime('%H:%M'),
        'location': i.location or '',
        'type': i.type or '',
        'is_locked': i.is_locked,
    }

def save_schedule(db: Session, user: User, day: date, schedule: list[dict]):
    old = db.query(ScheduleLog).filter(ScheduleLog.user_id == user.id, ScheduleLog.date == day).all()
    for log in old:
        db.delete(log)
    db.commit()
    log = ScheduleLog(user_id=user.id, date=day, schedule_json=schedule)
    db.add(log); db.commit(); db.refresh(log)
    for s in schedule:
        db.add(ScheduleItem(
            schedule_log_id=log.id,
            task_name=s['task'],
            start_time=parse_hhmm(s['start']),
            end_time=parse_hhmm(s['end']),
            location=s.get('location', ''),
            type=s.get('type', ''),
            is_locked=False,
        ))
    db.commit()
    return log

def rerun_for_user(db: Session, user: User, day: date):
    recovery = (
        db.query(RecoveryLog)
        .filter(RecoveryLog.user_id == user.id, RecoveryLog.date == day)
        .order_by(RecoveryLog.id.desc())
        .first()
    )
    band = recovery.readiness_band if recovery else 'MEDIUM'
    routines = db.query(Routine).filter(Routine.user_id == user.id).all()
    goals = db.query(Goal).filter(Goal.user_id == user.id, Goal.date == day).all()
    schedule = build_schedule(user, routines, goals, band)
    save_schedule(db, user, day, schedule)
    latest = (
        db.query(ScheduleLog)
        .filter(ScheduleLog.user_id == user.id, ScheduleLog.date == day)
        .order_by(ScheduleLog.id.desc())
        .first()
    )
    return [item_out(i) for i in latest.items]

@router.get('/schedule/today')
def today(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    log = (
        db.query(ScheduleLog)
        .filter(ScheduleLog.user_id == user.id, ScheduleLog.date == date.today())
        .order_by(ScheduleLog.id.desc())
        .first()
    )
    if not log:
        return rerun_for_user(db, user, date.today())
    return [item_out(i) for i in sorted(log.items, key=lambda x: x.start_time)]

@router.post('/schedule/rerun')
def rerun(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return rerun_for_user(db, user, date.today())

@router.patch('/schedule/items/{item_id}')
def patch_item(item_id: str, payload: ItemPatch, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    item = (
        db.query(ScheduleItem)
        .join(ScheduleLog)
        .filter(ScheduleItem.id == item_id, ScheduleLog.user_id == user.id)
        .first()
    )
    if not item:
        raise HTTPException(status_code=404, detail='Schedule item not found')
    if payload.start_time:
        start = datetime.strptime(payload.start_time, '%H:%M').time()
        old_minutes = item.end_time.hour * 60 + item.end_time.minute - item.start_time.hour * 60 - item.start_time.minute
        item.start_time = start
        total = start.hour * 60 + start.minute + old_minutes
        item.end_time = time(total // 60, total % 60)
    if payload.is_locked is not None:
        item.is_locked = payload.is_locked
    db.commit(); db.refresh(item)
    return item_out(item)

@router.post('/schedule/rate')
def rate(payload: RateIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    log = (
        db.query(ScheduleLog)
        .filter(ScheduleLog.user_id == user.id, ScheduleLog.date == date.today())
        .order_by(ScheduleLog.id.desc())
        .first()
    )
    if not log:
        raise HTTPException(status_code=404, detail='Schedule not found')
    log.rating = payload.rating; db.commit()
    return {'rating': payload.rating}

@router.post('/parse-input')
def parse_input(payload: ParseIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    tasks = parse_tasks(payload.text)
    for t in tasks:
        db.add(Goal(
            user_id=user.id,
            name=t.get('name', 'Task'),
            duration_minutes=int(t.get('duration_minutes', 60)),
            location_name=t.get('location_name'),
            priority=2,
            date=date.today(),
        ))
    db.commit()
    return rerun_for_user(db, user, date.today())

@router.get('/recovery/today')
def recovery_today(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    r = (
        db.query(RecoveryLog)
        .filter(RecoveryLog.user_id == user.id, RecoveryLog.date == date.today())
        .order_by(RecoveryLog.id.desc())
        .first()
    )
    if not r:
        return {
            'readiness_zone': 'normal',
            'readiness_band': 'MEDIUM',
            'predicted_hrv': 0,
            'baseline_hrv': 0,
            'shap_insight': 'No recovery data has been generated today',
        }
    return {
        'readiness_zone': r.readiness_zone,
        'readiness_band': r.readiness_band,
        'predicted_hrv': r.predicted_hrv,
        'baseline_hrv': r.baseline_hrv,
        'shap_insight': r.shap_insight,
    }

@router.get('/dev/simulate')
def simulate(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    data = fetch_wearable_data(user, db)
    rec = call_ml_service(data)
    db.add(RecoveryLog(
        user_id=user.id,
        date=date.today(),
        hrv_history=data['hrv_rmssd_ms'],
        hr_history=data['avg_hr_day_bpm'],
        sleep_history=data['sleep_duration_hours'],
        steps_history=data['steps'],
        **rec,
    ))
    db.commit()
    if not db.query(Routine).filter(Routine.user_id == user.id).first():
        db.add(Routine(user_id=user.id, name='Morning Prayer', start_time=time(6, 0), duration_minutes=30, location_name='Home'))
    if not db.query(Goal).filter(Goal.user_id == user.id, Goal.date == date.today()).first():
        db.add(Goal(user_id=user.id, name='Gym', duration_minutes=90, location_name='Gym', lat=24.7136, lng=46.6753, priority=3, date=date.today()))
        db.add(Goal(user_id=user.id, name='Study', duration_minutes=60, location_name='Home', priority=2, date=date.today()))
    db.commit()
    return rerun_for_user(db, user, date.today())
