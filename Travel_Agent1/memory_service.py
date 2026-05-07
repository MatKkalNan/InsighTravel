# memory_service.py
from __future__ import annotations

import os
import json
from datetime import datetime
from typing import Dict, Any, List, Optional

from dotenv import load_dotenv
from openai import OpenAI
from sqlalchemy.orm import Session

from models import UserMemory

load_dotenv()


# ---------------------------------------------
# OpenAI Client
# ---------------------------------------------
def get_openai_client() -> OpenAI:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise ValueError("OPENAI_API_KEY not set")
    return OpenAI(api_key=api_key)


# ---------------------------------------------
# Memory Type / Tool Mapping
# ---------------------------------------------
ALLOWED_MEMORY_TYPES = {
    "travel_style",
    "budget_preference",
    "flight_preference",
    "stay_preference",
    "destination_preference",
}

TOOL_MEMORY_TYPES = {
    "trip_ideation": ["travel_style", "budget_preference", "destination_preference"],
    "flight_search": ["flight_preference", "budget_preference", "destination_preference"],
    "stay_search": ["stay_preference", "budget_preference", "travel_style"],
    "accommodation_booking": ["stay_preference", "budget_preference"],
    "food_spot_search": ["travel_style", "destination_preference"],
    "budget_planner": ["budget_preference", "travel_style"],
    "local_guide": ["travel_style", "destination_preference"],
}


# ---------------------------------------------
# Trigger Rules
# ---------------------------------------------
MEMORY_TRIGGER_KEYWORDS = [
    "좋아",
    "선호",
    "싫어",
    "취향",
    "가성비",
    "럭셔리",
    "직항",
    "저가항공",
    "호텔",
    "에어비앤비",
    "조용한",
    "휴양",
    "자연",
    "도시 여행",
    "먹방",
    "국내 여행",
    "해외 여행",
    "예산",
    "비싼 건 싫",
    "부담돼",
    "바다 근처",
]


def should_extract_memory(user_message: str) -> bool:
    text = (user_message or "").strip()
    if len(text) < 5:
        return False
    return any(keyword in text for keyword in MEMORY_TRIGGER_KEYWORDS)


# ---------------------------------------------
# Prompt
# ---------------------------------------------
MEMORY_EXTRACTION_SYSTEM = """
너는 여행 사용자 장기 기억 추출기다.

역할:
- 사용자의 발화에서 장기적으로 재사용 가능한 여행 선호만 추출한다.
- 이번 턴에만 유효한 날짜, 임시 목적지, 단순 실행 요청은 저장하지 않는다.

저장 가능한 memory_type:
- travel_style
- budget_preference
- flight_preference
- stay_preference
- destination_preference

규칙:
1. 저장 가치가 없으면 should_store=false, memories=[]를 반환한다.
2. content는 사람이 읽을 수 있는 짧은 한국어 문장으로 쓴다.
3. importance는 1~5 정수.
4. JSON만 출력한다.

형식:
{
  "should_store": true,
  "memories": [
    {
      "memory_type": "travel_style",
      "content": "자연 위주 여행을 선호함",
      "importance": 4
    }
  ]
}
"""


# ---------------------------------------------
# Normalize Helpers
# ---------------------------------------------
def _safe_int(value: Any, default: int = 3) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def normalize_memory_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    should_store = bool(payload.get("should_store", False))
    raw_memories = payload.get("memories", [])

    if not isinstance(raw_memories, list):
        raw_memories = []

    memories: List[Dict[str, Any]] = []

    for item in raw_memories:
        if not isinstance(item, dict):
            continue

        memory_type = item.get("memory_type")
        content = (item.get("content") or "").strip()
        importance = _safe_int(item.get("importance"), default=3)
        importance = max(1, min(5, importance))

        if memory_type not in ALLOWED_MEMORY_TYPES:
            continue

        if not content:
            continue

        memories.append(
            {
                "memory_type": memory_type,
                "content": content,
                "importance": importance,
            }
        )

    return {
        "should_store": should_store and len(memories) > 0,
        "memories": memories,
    }


# ---------------------------------------------
# Extraction
# ---------------------------------------------
def extract_long_term_memory(
    user_message: str,
    context: str = "",
) -> Dict[str, Any]:
    """
    user_message에서 장기 기억으로 저장할 여행 선호를 추출
    """
    if not should_extract_memory(user_message):
        return {"should_store": False, "memories": []}

    user_prompt = f"""
[최근 대화 요약]
{context}

[사용자 발화]
{user_message}

이 발화에서 장기적으로 재사용 가능한 여행 선호를 추출하라.
"""

    try:
        client = get_openai_client()
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": MEMORY_EXTRACTION_SYSTEM},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0,
            response_format={"type": "json_object"},
        )
        parsed = json.loads(resp.choices[0].message.content or "{}")
        return normalize_memory_payload(parsed)

    except Exception as e:
        print(f"⚠️ memory extraction error: {e}")
        return {"should_store": False, "memories": []}

# ---------------------------------------------
# Survey Memory Builder
# ---------------------------------------------

def build_survey_memory_payload(answers: Dict[str, str]) -> Dict[str, Any]:
    if not answers:
        return {"should_store": False, "memories": []}

    memories: List[Dict[str, Any]] = []

    atmosphere = (answers.get("atmosphere") or "").strip()
    budget = (answers.get("budget") or "").strip()
    priority = (answers.get("priority") or "").strip()
    schedule = (answers.get("schedule") or "").strip()

    if atmosphere:
        memories.append({
            "memory_type": "travel_style",
            "content": f"{atmosphere} 여행 분위기를 선호함",
            "importance": 5,
        })
        memories.append({
            "memory_type": "destination_preference",
            "content": f"{atmosphere} 목적지를 선호함",
            "importance": 4,
        })

    if budget:
        memories.append({
            "memory_type": "budget_preference",
            "content": f"{budget} 예산 스타일을 선호함",
            "importance": 5,
        })

    if priority:
        memories.append({
            "memory_type": "travel_style",
            "content": f"여행에서 {priority}을(를) 중요하게 생각함",
            "importance": 4,
        })

    if schedule:
        memories.append({
            "memory_type": "travel_style",
            "content": f"{schedule} 일정 운영 방식을 선호함",
            "importance": 4,
        })

    return {
        "should_store": True,
        "memories": memories,
    }


def save_survey_long_term_memories(
    db: Session,
    user_id: int,
    source_message_id: Optional[int],
    answers: Dict[str, str],
) -> int:
    payload = build_survey_memory_payload(answers)

    return save_long_term_memories(
        db=db,
        user_id=user_id,
        source_message_id=source_message_id,
        memory_payload=payload,
    )

# ---------------------------------------------
# Save
# ---------------------------------------------
def save_long_term_memories(
    db: Session,
    user_id: int,
    source_message_id: Optional[int],
    memory_payload: Dict[str, Any],
) -> int:
    """
    중복 메모리는 content + memory_type 기준으로 저장 방지
    반환값: 새로 저장된 개수
    """
    if not memory_payload.get("should_store"):
        return 0

    saved_count = 0

    try:
        for mem in memory_payload.get("memories", []):
            memory_type = mem["memory_type"]
            content = mem["content"]
            importance = mem["importance"]

            existing = (
                db.query(UserMemory)
                .filter(
                    UserMemory.user_id == user_id,
                    UserMemory.memory_type == memory_type,
                    UserMemory.content == content,
                )
                .first()
            )

            if existing:
                existing.importance = max(existing.importance, importance)
                existing.updated_at = datetime.utcnow()
            else:
                row = UserMemory(
                    user_id=user_id,
                    memory_type=memory_type,
                    content=content,
                    importance=importance,
                    source_message_id=source_message_id,
                )
                db.add(row)
                saved_count += 1

        db.commit()
        return saved_count

    except Exception:
        db.rollback()
        raise


# ---------------------------------------------
# Load
# ---------------------------------------------
def load_all_long_term_memories(
    db: Session,
    user_id: int,
    limit: int = 20,
) -> Dict[str, Any]:
    rows = (
        db.query(UserMemory)
        .filter(UserMemory.user_id == user_id)
        .order_by(UserMemory.importance.desc(), UserMemory.updated_at.desc())
        .limit(limit)
        .all()
    )

    return {
        "memories": [
            {
                "memory_type": row.memory_type,
                "content": row.content,
                "importance": row.importance,
            }
            for row in rows
        ]
    }


def load_relevant_long_term_memory(
    db: Session,
    user_id: int,
    tool_name: str,
    limit: int = 10,
) -> Dict[str, Any]:
    wanted_types = TOOL_MEMORY_TYPES.get(tool_name, [])
    if not wanted_types:
        return {"memories": []}

    rows = (
        db.query(UserMemory)
        .filter(
            UserMemory.user_id == user_id,
            UserMemory.memory_type.in_(wanted_types),
        )
        .order_by(UserMemory.importance.desc(), UserMemory.updated_at.desc())
        .limit(limit)
        .all()
    )

    return {
        "memories": [
            {
                "memory_type": row.memory_type,
                "content": row.content,
                "importance": row.importance,
            }
            for row in rows
        ]
    }


# ---------------------------------------------
# Formatting
# ---------------------------------------------
def format_long_term_memory_for_prompt(memory_payload: Dict[str, Any]) -> str:
    memories = memory_payload.get("memories", [])
    if not memories:
        return ""

    lines = ["[사용자 장기 선호]"]
    for mem in memories[:5]:
        lines.append(f"- {mem['content']}")
    return "\n".join(lines)

