import math
from datetime import time, timedelta, datetime
from ortools.sat.python import cp_model
from services.maps import get_travel_minutes

HORIZON = 68
BASE_MINUTES = 6 * 60

def ceil_slots(minutes: int) -> int:
    return max(1, math.ceil(minutes / 15))

def time_to_slot(t: time) -> int:
    return max(0, min(HORIZON - 1, (t.hour * 60 + t.minute - BASE_MINUTES) // 15))

def slot_to_time(slot: int) -> str:
    minutes = BASE_MINUTES + slot * 15
    return f'{minutes // 60:02d}:{minutes % 60:02d}'

def item(task, start_slot, duration_slots, location, typ):
    return {'task': task, 'start': slot_to_time(start_slot), 'end': slot_to_time(start_slot + duration_slots), 'location': location or '', 'type': typ}

def routines_only(routines):
    result = []
    for r in routines:
        start = time_to_slot(r.start_time)
        result.append(item(r.name, start, ceil_slots(r.duration_minutes), r.location_name or 'Home', 'routine'))
    return sorted(result, key=lambda x: x['start'])

def is_home_goal(user, goal):
    if not goal.location_name or goal.location_name.lower() == 'home':
        return True
    if user.home_lat is not None and user.home_lng is not None and goal.lat is not None and goal.lng is not None:
        return abs(user.home_lat - goal.lat) < 0.0001 and abs(user.home_lng - goal.lng) < 0.0001
    return False

def build_schedule(user, routines, goals, readiness_band='MEDIUM'):
    fixed = routines_only(routines)
    if readiness_band == 'LOW':
        return fixed
    selected = sorted(goals, key=lambda g: g.priority or 1, reverse=True)
    if readiness_band == 'MEDIUM':
        selected = selected[:1]
    if not selected:
        return fixed

    model = cp_model.CpModel()
    intervals = []
    goal_meta = []
    for idx, r in enumerate(routines):
        start = time_to_slot(r.start_time)
        dur = ceil_slots(r.duration_minutes)
        if start + dur <= HORIZON:
            intervals.append(model.NewFixedSizeIntervalVar(start, dur, f'routine_{idx}'))

    for idx, g in enumerate(selected):
        goal_slots = ceil_slots(g.duration_minutes)
        travel_slots = 0
        prep_slots = 0
        if not is_home_goal(user, g):
            travel_slots = ceil_slots(get_travel_minutes(user.home_lat, user.home_lng, g.lat, g.lng))
            prep_slots = ceil_slots(getattr(user, 'prep_time_minutes', 30) or 30)
        total = prep_slots + travel_slots + goal_slots
        if total > HORIZON:
            return fixed
        start = model.NewIntVar(0, HORIZON - total, f'start_{idx}')
        intervals.append(model.NewIntervalVar(start, total, start + total, f'goal_block_{idx}'))
        goal_meta.append((g, start, prep_slots, travel_slots, goal_slots))

    model.AddNoOverlap(intervals)
    model.Maximize(sum((g.priority or 1) * 100 for g, _, _, _, _ in goal_meta) - sum(ts for _, _, _, ts, _ in goal_meta))
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = 5
    status = solver.Solve(model)
    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return fixed

    output = fixed[:]
    for g, start_var, prep_slots, travel_slots, goal_slots in goal_meta:
        start = int(solver.Value(start_var))
        cursor = start
        if prep_slots:
            output.append(item(f'Prep for {g.name}', cursor, prep_slots, 'Home', 'prep'))
            cursor += prep_slots
        if travel_slots:
            output.append(item(f'Travel to {g.name}', cursor, travel_slots, '', 'travel'))
            cursor += travel_slots
        output.append(item(g.name, cursor, goal_slots, g.location_name or 'Home', 'goal'))
    return sorted(output, key=lambda x: x['start'])

def parse_hhmm(value: str) -> time:
    return datetime.strptime(value, '%H:%M').time()
