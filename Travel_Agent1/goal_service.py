# goal_service.py
from __future__ import annotations
import os
import json
from dataclasses import dataclass
from typing import Optional, List
from dotenv import load_dotenv
from openai import OpenAI

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
# Goal Extraction Prompt
# -----------------------------
GOAL_EXTRACTION_SYSTEM = """
당신은 '여행 장기 목표 추출기'입니다.

역할:
- 사용자의 발화 + 기존 대화를 보고,
  지금 준비 중인 '대표 여행 1개'를 구조화하여 JSON으로 정리합니다.

주의:
- 여행과 무관한 내용(운동, 건강, 이직 등)은 무시합니다.
- 여러 여행이 섞여 있으면 가장 최근·가장 많이 언급된 '주 여행' 1개만 선택합니다.

출력 JSON 필드:
- destination: 나라/도시명 (예: "일본 오사카")
- nights: n박 m일 중 '박' 수 (정확하지 않으면 null)
- days: n박 m일 중 '일' 수 (정확하지 않으면 null)
- month: "3월", "겨울", "여름" 등 (없으면 null)
- budget_krw: 원 단위 예산 (없으면 null)
- style_tags: ["먹방","자연","휴양","도시"] 등 리스트
- status:
    - "just_started" (어디 갈지 고민 시작)
    - "choosing_city" (도시/국가 선택 중)
    - "planning_itinerary" (여행지는 확정 → 일정/숙소/예산 고민)
    - "done" (대부분 확정됨)
"""


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
    user_prompt = f"""
[CONTEXT]
{context}

[USER MESSAGE]
{user_message}

요구사항:
1) 위 두 정보를 바탕으로 현재 준비 중인 '대표 여행 1개'를 JSON으로 정리하세요.
2) JSON만 출력하세요. 주석/설명/마크다운 금지.
3) 불명확한 정보는 null 또는 []로 두세요.

이전 여행 목표(JSON):
{json.dumps(previous_goal, ensure_ascii=False) if previous_goal is not None else "null"}
"""

    resp = client.chat.completions.create(
        model="gpt-4.1-mini",
        messages=[
            {"role": "system", "content": GOAL_EXTRACTION_SYSTEM},
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
