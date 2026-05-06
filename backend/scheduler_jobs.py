import logging
from datetime import date, datetime, time, timedelta
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.date import DateTrigger
from database import SessionLocal
from models import Goal, RecoveryLog, Routine, ScheduleItem, ScheduleLog, User
from routes.schedule import rerun_for_user
from services.notifications import send_push
from services.recovery import call_ml_service
from services.wearables import fetch_wearable_data

scheduler = BackgroundScheduler(timezone='Asia/Riyadh')

def _today_recovery(db, user_id):
    return (
        db.query(RecoveryLog)
        .filter(RecoveryLog.user_id == user_id, RecoveryLog.date == date.today())
        .order_by(RecoveryLog.id.desc())
        .first()
    )

def _today_items_sorted(db, user_id):
    log = (
        db.query(ScheduleLog)
        .filter(ScheduleLog.user_id == user_id, ScheduleLog.date == date.today())
        .order_by(ScheduleLog.id.desc())
        .first()
    )
    if not log:
        return []
    return sorted(log.items, key=lambda x: x.start_time)

def schedule_leave_notifications(user: User, items):
    """For each TRAVEL block today, schedule a one-off push at the prep start."""
    today = date.today()
    prep_minutes = max(0, int(getattr(user, 'prep_time_minutes', 30) or 30))
    sorted_items = sorted(items, key=lambda x: x.start_time)
    for idx, it in enumerate(sorted_items):
        if (it.type or '').lower() != 'travel':
            continue
        goal_item = sorted_items[idx + 1] if idx + 1 < len(sorted_items) else None
        location = (goal_item.location if goal_item else it.location) or 'your destination'
        travel_minutes = (it.end_time.hour * 60 + it.end_time.minute) - (it.start_time.hour * 60 + it.start_time.minute)
        leave_dt = datetime.combine(today, it.start_time) - timedelta(minutes=prep_minutes)
        if leave_dt <= datetime.now():
            continue
        message = f'Leave for {location} in {prep_minutes} minutes (~{travel_minutes} min travel).'
        token = user.push_token
        job_id = f'leave_{user.id}_{it.id}'
        scheduler.add_job(
            send_push,
            trigger=DateTrigger(run_date=leave_dt),
            args=[token, message],
            id=job_id,
            replace_existing=True,
        )

def daily_recovery_job():
    db = SessionLocal()
    try:
        for user in db.query(User).all():
            try:
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
                rerun_for_user(db, user, date.today())
                items = _today_items_sorted(db, user.id)
                schedule_leave_notifications(user, items)
            except Exception as exc:
                logging.exception('Daily recovery failed for user %s: %s', user.id, exc)
                db.rollback()
    finally:
        db.close()

def morning_summary_job():
    db = SessionLocal()
    try:
        for user in db.query(User).all():
            try:
                rec = _today_recovery(db, user.id)
                zone = rec.readiness_zone if rec else 'normal'
                items = _today_items_sorted(db, user.id)
                first = items[0] if items else None
                if first:
                    msg = (
                        f'Good morning! Recovery: {zone}. '
                        f'First task: {first.task_name} at {first.start_time.strftime("%H:%M")}'
                    )
                else:
                    msg = f'Good morning! Recovery: {zone}. No tasks scheduled today.'
                send_push(user.push_token, msg)
            except Exception as exc:
                logging.exception('Morning summary failed for user %s: %s', user.id, exc)
    finally:
        db.close()

def promote_repeated_goals_job():
    db = SessionLocal()
    try:
        since = date.today() - timedelta(days=7)
        for user in db.query(User).all():
            counts: dict[str, int] = {}
            for goal in db.query(Goal).filter(Goal.user_id == user.id, Goal.date >= since).all():
                counts[goal.name] = counts.get(goal.name, 0) + 1
            for name, count in counts.items():
                exists = db.query(Routine).filter(Routine.user_id == user.id, Routine.name == name).first()
                if count >= 3 and not exists:
                    db.add(Routine(
                        user_id=user.id,
                        name=name,
                        start_time=time(18, 0),
                        duration_minutes=60,
                        location_name='Home',
                    ))
            db.commit()
    finally:
        db.close()

def start_scheduler():
    if not scheduler.running:
        scheduler.add_job(daily_recovery_job, 'cron', hour=6, minute=0, id='daily_recovery', replace_existing=True)
        scheduler.add_job(morning_summary_job, 'cron', hour=6, minute=10, id='morning_summary', replace_existing=True)
        scheduler.add_job(promote_repeated_goals_job, 'cron', hour=0, minute=0, id='promote_goals', replace_existing=True)
        scheduler.start()

def shutdown_scheduler():
    if scheduler.running:
        scheduler.shutdown()
