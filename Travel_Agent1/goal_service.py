from __future__ import annotations
import os
import json
from typing import Optional, List, Dict, Any
from dotenv import load_dotenv
from openai import OpenAI

from prompts import GOAL_EXTRACTION_SYSTEM, build_goal_extraction_user_prompt

load_dotenv()


def get_openai_client() -> OpenAI:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise ValueError("OPENAI_API_KEY not set")
    return OpenAI(api_key=api_key)


ALLOWED_STATUS = {
    "just_started",
    "choosing_city",
    "planning_itinerary",
    "done",
}


def _to_int(value: Any) -> Optional[int]:
    if value in (None, "", "null", "None"):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def normalize_trip_goal(goal: Optional[dict]) -> dict:
    goal = goal or {}

    destination = goal.get("destination")
    if destination in ("", "null", "None"):
        destination = None

    month = goal.get("month")
    if month in ("", "null", "None"):
        month = None

    budget_krw = _to_int(goal.get("budget_krw"))
    nights = _to_int(goal.get("nights"))
    days = _to_int(goal.get("days"))

    style_tags = goal.get("style_tags", [])
    if style_tags in (None, "", "null", "None"):
        style_tags = []
    elif isinstance(style_tags, str):
        style_tags = [s.strip() for s in style_tags.split(",") if s.strip()]
    elif not isinstance(style_tags, list):
        style_tags = []

    status = goal.get("status")
    if status not in ALLOWED_STATUS:
        status = "just_started"

    return {
        "destination": destination,
        "nights": nights,
        "days": days,
        "month": month,
        "budget_krw": budget_krw,
        "style_tags": style_tags,
        "status": status,
    }


def merge_trip_goal(previous_goal: Optional[dict], new_goal: Optional[dict]) -> dict:
    prev = normalize_trip_goal(previous_goal)
    new = normalize_trip_goal(new_goal)

    merged = prev.copy()

    for key in ["destination", "nights", "days", "month", "budget_krw", "status"]:
        if new.get(key) not in (None, "", [], {}):
            merged[key] = new[key]

    prev_tags = prev.get("style_tags", []) or []
    new_tags = new.get("style_tags", []) or []
    merged["style_tags"] = list(dict.fromkeys(prev_tags + new_tags))

    return merged


def extract_trip_goal_from_text(
    user_message: str,
    context: str = "",
    previous_goal: Optional[dict] = None,
) -> dict:
    user_prompt = build_goal_extraction_user_prompt(context, user_message, previous_goal)

    client = get_openai_client()

    try:
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": GOAL_EXTRACTION_SYSTEM},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.1,
            response_format={"type": "json_object"},
        )
        raw = (resp.choices[0].message.content or "").strip()
        parsed = json.loads(raw)
    except Exception as e:
        print(f"⚠️ Goal extraction error: {e}")
        parsed = {}

    new_goal = normalize_trip_goal(parsed)

    if previous_goal:
        return merge_trip_goal(previous_goal, new_goal)

    return new_goal