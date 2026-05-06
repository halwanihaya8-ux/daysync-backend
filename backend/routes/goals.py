from datetime import date as date_cls
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session
from auth import get_current_user
from database import get_db
from models import Goal, User

router = APIRouter(prefix='/goals')

class GoalIn(BaseModel):
    name: str
    duration_minutes: int
    location_name: str | None = None
    lat: float | None = None
    lng: float | None = None
    priority: int = 1
    date: str | None = None

def out(g: Goal):
    return {
        'id': g.id,
        'name': g.name,
        'duration_minutes': g.duration_minutes,
        'location_name': g.location_name,
        'lat': g.lat,
        'lng': g.lng,
        'priority': g.priority,
        'date': g.date.isoformat(),
    }

@router.post('')
def create(payload: GoalIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    day = date_cls.fromisoformat(payload.date) if payload.date else date_cls.today()
    g = Goal(
        user_id=user.id,
        name=payload.name,
        duration_minutes=payload.duration_minutes,
        location_name=payload.location_name,
        lat=payload.lat,
        lng=payload.lng,
        priority=payload.priority,
        date=day,
    )
    db.add(g); db.commit(); db.refresh(g)
    return out(g)

@router.get('')
def list_goals(
    date_str: str | None = Query(default=None, alias='date'),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    day = date_cls.fromisoformat(date_str) if date_str else date_cls.today()
    return [out(g) for g in db.query(Goal).filter(Goal.user_id == user.id, Goal.date == day).all()]

@router.delete('/{goal_id}')
def delete(goal_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    g = db.query(Goal).filter(Goal.id == goal_id, Goal.user_id == user.id).first()
    if not g:
        raise HTTPException(status_code=404, detail='Goal not found')
    db.delete(g); db.commit()
    return {'deleted': goal_id}
