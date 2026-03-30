# goal_service.py
from __future__ import annotations
import os
import json
from dataclasses import dataclass
from typing import Optional, List
from dotenv import load_dotenv
from openai import OpenAI

# 👉 시스템 프롬프트 및 빌더 임포트
from prompts import GOAL_EXTRACTION_SYSTEM, build_goal_extraction_user_prompt

load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# -----------------------------
# TripGoal 데이터 구조 정의
# -----------------------------
@dataclass
class TripGoal:
    destination: Optional[str] = None      
    nights: Optional[int] = None           
    days: Optional[int] = None             
    month: Optional[str] = None            
    budget_krw: Optional[int] = None       
    style_tags: Optional[List[str]] = None 
    status: Optional[str] = None           


# -----------------------------
# Goal Extraction Function
# -----------------------------
def extract_trip_goal_from_text(
    user_message: str,
    context: str = "",
    previous_goal: Optional[dict] = None,
) -> dict:
    
    # 👉 프롬프트 빌더 함수 사용
    user_prompt = build_goal_extraction_user_prompt(context, user_message, previous_goal)

    resp = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": GOAL_EXTRACTION_SYSTEM},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.1,
    )

    raw = (resp.choices[0].message.content or "").strip()

    try:
        new_goal = json.loads(raw)
    except Exception:
        new_goal = {
            "destination": None,
            "nights": None,
            "days": None,
            "month": None,
            "budget_krw": None,
            "style_tags": [],
            "status": "just_started",
        }

    if previous_goal:
        merged = previous_goal.copy()
        for k, v in new_goal.items():
            if v not in (None, "", [], {}):
                merged[k] = v
        return merged

    return new_goal
