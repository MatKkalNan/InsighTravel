# planner.py
import os
import json
from typing import Dict, Any

from dotenv import load_dotenv
from openai import OpenAI

# 👉 prompts.py에서 시스템 프롬프트와 빌더 함수 임포트
from prompts import PLANNER_SYSTEM_PROMPT, build_planner_user_prompt

load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

def _call_planner_llm(planner_context: str, user_message: str, memory_context: str = "") -> str:
    """
    LLM을 한 번 호출해서 JSON 문자열(또는 JSON처럼 생긴 텍스트)을 받아온다.
    """
    # 👉 프롬프트 빌더 함수 사용
    user_prompt = build_planner_user_prompt(planner_context, user_message, memory_context)

    print("[DEBUG] planner user_prompt preview:")
    print(user_prompt[:1000])
    
    resp = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": PLANNER_SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.2,
    )
    return (resp.choices[0].message.content or "").strip()

def plan_tasks(planner_context: str, user_message: str, memory_context: str = "") -> Dict[str, Any]:
    """
    메인 플래너 함수.
    """
    # 1) 아주 간단한 rule 기반으로 '완전 여행 밖'인 경우 빠르게 out_of_scope로 처리
    lower = user_message.lower()
    normalized = lower.strip()
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
            "args": {},
        }
    # 1.5) 짧은 인사/감탄/단순 응답은 memory_context에 끌려 여행 추천으로 오판되지 않도록 general_chat으로 고정
    smalltalk_inputs = {
    "안녕", "안녕하세요", "하이", "ㅎㅇ", "반가워",
    "고마워", "감사", "감사해", "고맙다",
    "오케이", "오키", "ㅇㅋ", "응", "네", "넵",
    "좋아", "좋네", "ㅋㅋ", "ㅎㅎ",
    "아", "음", "흠", "잠시만", "잠깐만"
    }

    if normalized in smalltalk_inputs:
        return {
            "intent": "general_chat",
            "tools": ["general_chat"],
            "subtasks": ["사용자와 자연스럽게 대화를 이어가며 여행 계획을 도울 준비를 한다."],
            "trip_stage": "ideation",
            "args": {},
        }
    # 2) LLM에게 맡겨서 plan JSON 생성
    raw = _call_planner_llm(planner_context, user_message, memory_context)

    # 3) JSON 파싱 시도
    try:
        plan = json.loads(raw)
    except Exception:
        try:
            start = raw.index("{")
            end = raw.rindex("}") + 1
            plan = json.loads(raw[start:end])
        except Exception:
            plan = {
                "intent": "general_chat",
                "tools": ["general_chat"],
                "subtasks": ["사용자의 여행 고민을 듣고 다음에 무엇을 정하면 좋을지 도와준다."],
                "trip_stage": "ideation",
                "args": {},
            }

    # 4) 보정: 필드 누락/형식 이상 시 기본값 채우기
    intent = plan.get("intent") or "general_chat"
    tools = plan.get("tools") or [intent]
    if isinstance(tools, str):
        tools = [tools]
    subtasks = plan.get("subtasks") or ["사용자의 여행 고민에 맞춰 다음 단계를 함께 정한다."]
    trip_stage = plan.get("trip_stage") or "ideation"

    args = plan.get("args") or {}
    if not isinstance(args, dict):
        args = {}

    cleaned = {
        "intent": intent,
        "tools": tools,
        "subtasks": subtasks,
        "trip_stage": trip_stage,
        "args": args,
    }
    return cleaned