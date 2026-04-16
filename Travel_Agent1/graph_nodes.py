# graph_nodes.py
import os
import json
from pyexpat.errors import messages
from typing import Dict, Any

from dotenv import load_dotenv
from openai import OpenAI

from graph_state import ChatState
import planner
import tools
from goal_service import extract_trip_goal_from_text
from prompts import build_context_summary_prompt

load_dotenv()


def get_openai_client() -> OpenAI:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise ValueError("OPENAI_API_KEY not set")
    return OpenAI(api_key=api_key)


# ---------------------------------------------
# 1) 컨텍스트 요약 노드
# ---------------------------------------------
def context_node(state: ChatState) -> ChatState:
    messages = state.get("messages", [])
    if not messages:
        return state

    last_msgs = messages[-6:]
    convo_text = "\n".join(f"{m['role']}: {m['content']}" for m in last_msgs)

    # 기존 summary가 있으면 우선 사용
    current_context = state.get("context", "") or state.get("short_memory_summary", "") or ""

    summary_prompt = build_context_summary_prompt(current_context, convo_text)

    try:
        client = get_openai_client()
        summary_res = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": summary_prompt}],
            temperature=0.2,
        )
        new_summary = (summary_res.choices[0].message.content or "").strip()
        if new_summary:
            state["context"] = new_summary
            state["short_memory_summary"] = new_summary
    except Exception as e:
        print(f"⚠️ context_node summary error: {e}")
        # 에러시 기존 유지
        pass

    return state


# ---------------------------------------------
# 2) 여행 목표 관리 노드
# ---------------------------------------------
def goal_node(state: ChatState) -> ChatState:
    messages = state.get("messages", [])
    if not messages:
        return state

    last_user_msg = messages[-1]["content"]
    context_str = state.get("context", "") or ""

    prev_goal = state.get("trip_goal")
    if not isinstance(prev_goal, dict):
        prev_goal = None

    try:
        new_goal = extract_trip_goal_from_text(
            user_message=last_user_msg,
            context=context_str,
            previous_goal=prev_goal,
        )
        state["trip_goal"] = new_goal
    except Exception as e:
        print(f"⚠️ goal_node extraction error: {e}")
        if prev_goal is not None:
            state["trip_goal"] = prev_goal
        else:
            state["trip_goal"] = {
                "destination": None,
                "nights": None,
                "days": None,
                "month": None,
                "budget_krw": None,
                "style_tags": [],
                "status": "just_started",
            }

    return state


# ---------------------------------------------
# 3) 플래너 노드
# ---------------------------------------------
def planner_node(state: ChatState) -> ChatState:
    messages = state.get("messages", [])
    if not messages:
        return state

    latest_user_msg = messages[-1]["content"]

    context_summary = state.get("context", "") or ""
    trip_goal = state.get("trip_goal") or {}
    trip_profile = state.get("trip_profile") or {}
    constraints = state.get("constraints") or {}

    # 장기 기억은 planner에 과하게 넣지 않는 게 보통 낫지만,
    # 데모 단계에서는 아주 짧게만 넣어도 됨.
    long_term_memory = state.get("long_term_memory") or {}

    memory_context = state.get("memory_context", "")

    combined_context = f"""
[대화 요약]
{context_summary}

[여행 목표]
{json.dumps(trip_goal, ensure_ascii=False)}

[현재 여행 상태]
{json.dumps(trip_profile, ensure_ascii=False)}

[누적 조건]
{json.dumps(constraints, ensure_ascii=False)}

[장기 기억(참고용)]
{json.dumps(long_term_memory, ensure_ascii=False)}
""".strip()

    try:
        plan = planner.plan_tasks(combined_context, latest_user_msg, memory_context)
    except Exception as e:
        print(f"⚠️ planner_node error: {e}")
        plan = {
            "intent": "general_chat",
            "tools": ["general_chat"],
            "subtasks": [],
            "trip_stage": "planning",
            "args": {},
        }

    if not isinstance(plan, dict):
        plan = {
            "intent": "general_chat",
            "tools": ["general_chat"],
            "subtasks": [],
            "trip_stage": "planning",
            "args": {},
        }

    plan["original_user_message"] = latest_user_msg
    state["plan"] = plan
    return state


# ---------------------------------------------
# 4) 장기 기억 게이트 노드 - 플래너에서 필요한 기억 유형만 선별해서 컨텍스트로 제공
# ---------------------------------------------
def memory_gate_node(state):
    messages = state.get("messages", [])
    if not messages:
     return state

    user_message = messages[-1].get("content", "")
    memories = (state.get("long_term_memory") or {}).get("memories", [])

    selected_types = []

    if any(k in user_message for k in ["추천", "여행지", "도시"]):
        selected_types = ["destination_preference", "travel_style", "budget_preference"]

    elif any(k in user_message for k in ["숙소", "호텔"]):
        selected_types = ["budget_preference", "travel_style"]

    elif any(k in user_message for k in ["일정", "코스"]):
        selected_types = ["travel_style"]

    elif any(k in user_message for k in ["항공", "항공권"]):
        selected_types = ["budget_preference"]

    else:
        selected_types = []

    filtered = [
        m for m in memories
        if m.get("memory_type") in selected_types
    ]

    memory_context = ""
    if filtered:
        memory_context = "[사용자 여행 성향]\n" + "\n".join(
            f"- {m['content']}" for m in filtered
        )

    state["memory_context"] = memory_context
    state["relevant_long_term_memory"] = filtered
    state["memory_gate"] = {
        "use_memory": len(filtered) > 0,
        "types": selected_types,
    }

    return state


# ---------------------------------------------
# 5) 도구 실행 노드
# ---------------------------------------------
def tool_node(state: ChatState) -> ChatState:
    plan = state.get("plan", {}) or {}
    context = state.get("context", "") or ""
    weather_data = state.get("weather_data")
    long_term_memory = state.get("long_term_memory")
    survey = state.get("survey")

    try:
        answer = tools.run_tools_from_plan(
            plan=plan,
            context=context,
            weather_data=weather_data,
            long_term_memory=long_term_memory,
            survey=survey,
        )
    except TypeError:
        # 아직 tools.py 시그니처를 안 바꿨다면 fallback
        answer = tools.run_tools_from_plan(plan, context)

    state["tool_output"] = answer

    if "messages" not in state or state["messages"] is None:
        state["messages"] = []

    state["messages"].append({"role": "assistant", "content": answer})

    # 최소한의 tool_results 기록
    tool_name = ((plan.get("tools") or ["general_chat"])[0])
    existing_results = state.get("tool_results") or {}
    existing_results[tool_name] = {
        "status": "ok",
        "data": answer,
        "evidence": None,
        "retry_hint": None,
    }
    state["tool_results"] = existing_results

    return state