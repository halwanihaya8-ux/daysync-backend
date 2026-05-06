import uuid
from sqlalchemy import Boolean, Column, Date, DateTime, Float, ForeignKey, Integer, JSON, String, Time, UniqueConstraint, func
from sqlalchemy.orm import relationship
from database import Base

def new_uuid():
    return str(uuid.uuid4())

class User(Base):
    __tablename__ = 'users'
    id = Column(String, primary_key=True, default=new_uuid)
    email = Column(String, unique=True, nullable=False, index=True)
    password_hash = Column(String, nullable=False)
    timezone = Column(String, default='Asia/Riyadh')
    prep_time_minutes = Column(Integer, default=30)
    push_token = Column(String, nullable=True)
    home_lat = Column(Float, nullable=True)
    home_lng = Column(Float, nullable=True)
    webhook_token = Column(String, unique=True, default=new_uuid, nullable=False, index=True)

class Routine(Base):
    __tablename__ = 'routines'
    id = Column(String, primary_key=True, default=new_uuid)
    user_id = Column(String, ForeignKey('users.id'), nullable=False, index=True)
    name = Column(String, nullable=False)
    start_time = Column(Time, nullable=False)
    duration_minutes = Column(Integer, nullable=False)
    location_name = Column(String, nullable=True)
    lat = Column(Float, nullable=True)
    lng = Column(Float, nullable=True)

class Goal(Base):
    __tablename__ = 'goals'
    id = Column(String, primary_key=True, default=new_uuid)
    user_id = Column(String, ForeignKey('users.id'), nullable=False, index=True)
    name = Column(String, nullable=False)
    duration_minutes = Column(Integer, nullable=False)
    location_name = Column(String, nullable=True)
    lat = Column(Float, nullable=True)
    lng = Column(Float, nullable=True)
    priority = Column(Integer, default=1)
    date = Column(Date, nullable=False, index=True)

class RecoveryLog(Base):
    __tablename__ = 'recovery_logs'
    id = Column(String, primary_key=True, default=new_uuid)
    user_id = Column(String, ForeignKey('users.id'), nullable=False, index=True)
    date = Column(Date, nullable=False, index=True)
    hrv_history = Column(JSON, nullable=True)
    hr_history = Column(JSON, nullable=True)
    sleep_history = Column(JSON, nullable=True)
    steps_history = Column(JSON, nullable=True)
    readiness_zone = Column(String, nullable=True)
    readiness_band = Column(String, nullable=True)
    predicted_hrv = Column(Float, nullable=True)
    baseline_hrv = Column(Float, nullable=True)
    shap_insight = Column(String, nullable=True)

class ScheduleLog(Base):
    __tablename__ = 'schedule_logs'
    id = Column(String, primary_key=True, default=new_uuid)
    user_id = Column(String, ForeignKey('users.id'), nullable=False, index=True)
    date = Column(Date, nullable=False, index=True)
    schedule_json = Column(JSON, nullable=True)
    rating = Column(Integer, nullable=True)
    items = relationship('ScheduleItem', cascade='all, delete-orphan')

class ScheduleItem(Base):
    __tablename__ = 'schedule_items'
    id = Column(String, primary_key=True, default=new_uuid)
    schedule_log_id = Column(String, ForeignKey('schedule_logs.id'), nullable=False, index=True)
    task_name = Column(String, nullable=False)
    start_time = Column(Time, nullable=False)
    end_time = Column(Time, nullable=False)
    location = Column(String, nullable=True)
    type = Column(String, nullable=True)
    is_locked = Column(Boolean, default=False)

class HealthSample(Base):
    """One row per (user, metric, day). Upserted by webhook ingestion."""
    __tablename__ = 'health_samples'
    __table_args__ = (UniqueConstraint('user_id', 'metric', 'date', name='uq_user_metric_date'),)
    id = Column(String, primary_key=True, default=new_uuid)
    user_id = Column(String, ForeignKey('users.id'), nullable=False, index=True)
    metric = Column(String, nullable=False, index=True)  # 'hrv' | 'hr' | 'sleep' | 'steps'
    date = Column(Date, nullable=False, index=True)
    value = Column(Float, nullable=False)
    sample_count = Column(Integer, default=1)  # how many raw points contributed
    source = Column(String, nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
