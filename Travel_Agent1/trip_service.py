from datetime import datetime
from typing import Optional, Dict, Any, Tuple

from sqlalchemy.orm import Session
from models import Trip


def load_latest_trip(db: Session, user_id: int) -> Optional[Trip]:
    return (
        db.query(Trip)
        .filter(Trip.user_id == user_id)
        .order_by(Trip.updated_at.desc())
        .first()
    )


def upsert_trip_from_state(
    db: Session,
    user_id: int,
    state: Dict[str, Any],
) -> Trip:
    trip_goal = state.get("trip_goal") or {}
    trip_profile = state.get("trip_profile") or {}
    constraints = state.get("constraints") or {}

    if not isinstance(trip_goal, dict):
        trip_goal = {}
    if not isinstance(trip_profile, dict):
        trip_profile = {}
    if not isinstance(constraints, dict):
        constraints = {}

    trip = load_latest_trip(db, user_id)
    if not trip:
        trip = Trip(user_id=user_id)
        db.add(trip)

    destination = trip_profile.get("destination") or trip_goal.get("destination")
    nights = trip_profile.get("nights") or trip_goal.get("nights")
    days = trip_profile.get("days") or trip_goal.get("days")

    if destination not in (None, "", []):
        trip.destination = destination

    if trip_profile.get("start_date") not in (None, "", []):
        trip.start_date = trip_profile.get("start_date")

    if trip_profile.get("end_date") not in (None, "", []):
        trip.end_date = trip_profile.get("end_date")

    if nights not in (None, "", []):
        trip.nights = _safe_int(nights, default=trip.nights)

    if days not in (None, "", []):
        trip.days = _safe_int(days, default=trip.days)

    if trip_profile.get("travelers") not in (None, "", []):
        trip.travelers = _safe_int(trip_profile.get("travelers"), default=trip.travelers)

    if trip_profile.get("departure_city") not in (None, "", []):
        trip.departure_city = trip_profile.get("departure_city")

    if trip_goal:
        trip.trip_goal_json = trip_goal

    if constraints:
        trip.constraints_json = constraints

    status = trip_goal.get("status")
    if status not in (None, "", []):
        trip.status = status

    trip.updated_at = datetime.utcnow()

    try:
        db.commit()
        db.refresh(trip)
        return trip
    except Exception:
        db.rollback()
        raise


def trip_to_state_payload(
    trip: Optional[Trip],
) -> Tuple[Optional[dict], Optional[dict], Optional[dict]]:
    if not trip:
        return None, None, None

    trip_goal = trip.trip_goal_json if trip.trip_goal_json else None
    constraints = trip.constraints_json if trip.constraints_json else None

    trip_profile = {
        "destination": trip.destination,
        "start_date": trip.start_date,
        "end_date": trip.end_date,
        "nights": trip.nights,
        "days": trip.days,
        "travelers": trip.travelers,
        "departure_city": trip.departure_city,
    }

    if not any(v is not None for v in trip_profile.values()):
        trip_profile = None

    return trip_goal, trip_profile, constraints


def _safe_int(value: Any, default: Optional[int] = None) -> Optional[int]:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default