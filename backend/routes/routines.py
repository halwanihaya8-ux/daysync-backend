from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from auth import get_current_user
from database import get_db
from models import Routine, User

router = APIRouter(prefix='/routines')

class RoutineIn(BaseModel):
    name: str
    start_time: str
    duration_minutes: int
    location_name: str | None = None
    lat: float | None = None
    lng: float | None = None

def out(r: Routine):
    return {'id': r.id, 'name': r.name, 'start_time': r.start_time.strftime('%H:%M'), 'duration_minutes': r.duration_minutes, 'location_name': r.location_name, 'lat': r.lat, 'lng': r.lng}

@router.post('')
def create(payload: RoutineIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    r = Routine(user_id=user.id, name=payload.name, start_time=datetime.strptime(payload.start_time, '%H:%M').time(), duration_minutes=payload.duration_minutes, location_name=payload.location_name, lat=payload.lat, lng=payload.lng)
    db.add(r); db.commit(); db.refresh(r)
    return out(r)

@router.get('')
def list_routines(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return [out(r) for r in db.query(Routine).filter(Routine.user_id == user.id).all()]

@router.delete('/{routine_id}')
def delete(routine_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    r = db.query(Routine).filter(Routine.id == routine_id, Routine.user_id == user.id).first()
    if not r:
        raise HTTPException(status_code=404, detail='Routine not found')
    db.delete(r); db.commit()
    return {'deleted': routine_id}
