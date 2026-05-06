import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from database import Base, engine
from routes import goals, health, routines, schedule, users
from scheduler_jobs import shutdown_scheduler, start_scheduler

logging.basicConfig(level=logging.INFO)

@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    start_scheduler()
    yield
    shutdown_scheduler()

app = FastAPI(title='DaySync AI MVP', lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=['*'], allow_credentials=True, allow_methods=['*'], allow_headers=['*'])
app.include_router(users.router)
app.include_router(routines.router)
app.include_router(goals.router)
app.include_router(schedule.router)
app.include_router(health.router)

@app.get('/')
def root():
    return {'status': 'ok', 'service': 'DaySync AI MVP'}
