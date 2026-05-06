import uuid
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from auth import create_token, get_current_user, hash_password, verify_password
from database import get_db
from models import User

router = APIRouter()

class AuthIn(BaseModel):
    email: str
    password: str

class UserPatch(BaseModel):
    timezone: str | None = None
    prep_time_minutes: int | None = None
    push_token: str | None = None
    home_lat: float | None = None
    home_lng: float | None = None

def user_out(user: User):
    return {
        'id': user.id,
        'email': user.email,
        'timezone': user.timezone,
        'prep_time_minutes': user.prep_time_minutes,
        'home_lat': user.home_lat,
        'home_lng': user.home_lng,
        'webhook_token': user.webhook_token,
    }

@router.post('/auth/register')
def register(payload: AuthIn, db: Session = Depends(get_db)):
    if db.query(User).filter(User.email == payload.email).first():
        raise HTTPException(status_code=400, detail='Email already registered')
    user = User(
        email=payload.email,
        password_hash=hash_password(payload.password),
        webhook_token=str(uuid.uuid4()),
    )
    db.add(user); db.commit(); db.refresh(user)
    return {'token': create_token(user.id), 'user_id': user.id, 'webhook_token': user.webhook_token}

@router.post('/auth/login')
def login(payload: AuthIn, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == payload.email).first()
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail='Invalid email or password')
    return {'token': create_token(user.id), 'user_id': user.id, 'webhook_token': user.webhook_token}

@router.get('/users/me')
def me(user: User = Depends(get_current_user)):
    return user_out(user)

@router.patch('/users/me')
def update_me(payload: UserPatch, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(user, key, value)
    db.commit(); db.refresh(user)
    return user_out(user)
