from __future__ import annotations
import os
import json
from dataclasses import dataclass
from typing import Optional, List
from dotenv import load_dotenv
from openai import OpenAI

# [변경] 프롬프트 모듈 임포트
from prompts.goal_prompts import GOAL_EXTRACTION_SYSTEM, get_goal_extraction_user_prompt

load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


# -----------------------------
# TripGoal 데이터 구조 정의
# -----------------------------
@dataclass
class TripGoal:
    destination: Optional[str] = None      # 예: "일본 오사카", "베트남 다낭"
    nights: Optional[int] = None           # 3박 4일 → 3
    days: Optional[int] = None             # 3박 4일 → 4
    month: Optional[str] = None            # "3월", "10월", "봄" 등
    budget_krw: Optional[int] = None       # 총 예산 (원 단위)
    style_tags: Optional[List[str]] = None # ["먹방","도시","휴양"]
    status: Optional[str] = None           # just_started, choosing_city, planning_itinerary, done


# -----------------------------
# Goal Extraction Function
# -----------------------------
def extract_trip_goal_from_text(
    user_message: str,
    context: str = "",
    previous_goal: Optional[dict] = None,
) -> dict:
    """
    user_message + context를 기반으로 현재 TripGoal JSON을 생성.
    previous_goal이 있으면 null/빈 값이 아닌 필드만 덮어쓰는 merge 로직 포함.
    """
    
    # [변경] 하드코딩 제거 -> 프롬프트 함수 호출
    user_prompt = get_goal_extraction_user_prompt(user_message, context, previous_goal)

    resp = client.chat.completions.create(
        model="gpt-4.1-mini",
        messages=[
            {"role": "system", "content": GOAL_EXTRACTION_SYSTEM}, # [변경] 모듈 변수 사용
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.1,
    )

    raw = (resp.choices[0].message.content or "").strip()

    # JSON 파싱 실패 대비
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

    # merge: previous_goal이 있으면 채워진 필드만 덮어쓰기
    if previous_goal:
        merged = previous_goal.copy()
        for k, v in new_goal.items():
            if v not in (None, "", [], {}):
                merged[k] = v
        return merged

    return new_goal