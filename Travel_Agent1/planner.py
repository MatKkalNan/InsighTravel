import os
import json
from typing import Dict, Any

from dotenv import load_dotenv
from openai import OpenAI

# [변경] 프롬프트 모듈 임포트
from prompts.planner_prompts import PLANNER_SYSTEM, get_planner_user_prompt

load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


def _call_planner_llm(planner_context: str, user_message: str) -> str:
    """
    LLM을 한 번 호출해서 JSON 문자열(또는 JSON처럼 생긴 텍스트)을 받아온다.
    """
    # [변경] 하드코딩 제거 -> 프롬프트 함수 호출
    user_prompt = get_planner_user_prompt(planner_context, user_message)

    resp = client.chat.completions.create(
        model="gpt-4.1-mini",
        messages=[
            {"role": "system", "content": PLANNER_SYSTEM}, # [변경] 모듈 변수 사용
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.2,
    )
    return (resp.choices[0].message.content or "").strip()


def plan_tasks(planner_context: str, user_message: str) -> Dict[str, Any]:
    """
    메인 플래너 함수.
    """
    # 1) 아주 간단한 rule 기반으로 '완전 여행 밖'인 경우 빠르게 out_of_scope로 처리
    lower = user_message.lower()
    if any(
        kw in lower
        for kw in [
            "헬스", "운동", "다이어트", "주식", "코인", "투자",
            "이직", "퇴사", "연애", "썸", "코딩", "프로그래밍",
        ]
    ) and "여행" not in lower and "trip" not in lower:
        return {
            "intent": "out_of_scope",
            "tools": ["out_of_scope"],
            "subtasks": ["여행 범위를 벗어난 질문임을 알리고, 여행 주제로 다시 유도한다."],
            "trip_stage": "ideation",
        }

    # 2) LLM에게 맡겨서 plan JSON 생성
    raw = _call_planner_llm(planner_context, user_message)

    # 3) JSON 파싱 시도
    try:
        plan = json.loads(raw)
    except Exception:
        # 혹시 텍스트 안에 { ... }만 골라낼 수 있으면 골라서 다시 시도
        try:
            start = raw.index("{")
            end = raw.rindex("}") + 1
            plan = json.loads(raw[start:end])
        except Exception:
            # 완전히 실패하면 안전한 fallback
            plan = {
                "intent": "general_chat",
                "tools": ["general_chat"],
                "subtasks": ["사용자의 여행 고민을 듣고 다음에 무엇을 정하면 좋을지 도와준다."],
                "trip_stage": "ideation",
            }

    # 4) 보정: 필드 누락/형식 이상 시 기본값 채우기
    intent = plan.get("intent") or "general_chat"
    tools = plan.get("tools") or [intent]
    if isinstance(tools, str):
        tools = [tools]
    subtasks = plan.get("subtasks") or ["사용자의 여행 고민에 맞춰 다음 단계를 함께 정한다."]
    trip_stage = plan.get("trip_stage") or "ideation"

    cleaned = {
        "intent": intent,
        "tools": tools,
        "subtasks": subtasks,
        "trip_stage": trip_stage,
    }
    return cleaned