# graph_nodes.py
import os
import json
from typing import Dict, Any

from dotenv import load_dotenv
from openai import OpenAI

from graph_state import ChatState
import planner
import tools
from goal_service import extract_trip_goal_from_text

# 👉 요약 프롬프트 빌더 임포트
from prompts import build_context_summary_prompt

load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# ---------------------------------------------
# 1) 컨텍스트 요약 노드 (OpenAI)
# ---------------------------------------------
def context_node(state: ChatState) -> ChatState:
    messages = state.get("messages", [])
    if not messages:
        return state

    last_msgs = messages[-6:]
    convo_text = "\n".join(f"{m['role']}: {m['content']}" for m in last_msgs)
    current_context = state.get("context", "")

    # 👉 동적으로 프롬프트 생성
    summary_prompt = build_context_summary_prompt(current_context, convo_text)

    try:
        summary_res = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": summary_prompt}],
            temperature=0.2,
        )
        state["context"] = summary_res.choices[0].message.content.strip()
    except:
        pass # 에러시 기존 유지

    return state


# ---------------------------------------------
# 2) [신규] 여행 목표 관리 노드
# ---------------------------------------------
def goal_node(state: ChatState) -> ChatState:
    messages = state.get("messages", [])
    if not messages:
        return state

    last_user_msg = messages[-1]["content"]
    context_str = state.get("context", "")
    
    # 이전 목표 로드
    prev_goal = state.get("trip_goal")
    if isinstance(prev_goal, str):
        try: prev_goal = json.loads(prev_goal)
        except: prev_goal = None

    # goal_service를 통해 업데이트
    new_goal = extract_trip_goal_from_text(last_user_msg, context_str, prev_goal)
    
    state["trip_goal"] = new_goal
    return state


# ---------------------------------------------
# 3) 플래너 노드 (OpenAI)
# ---------------------------------------------
def planner_node(state: ChatState) -> ChatState:
    messages = state.get("messages", [])
    latest_user_msg = messages[-1]["content"]
    
    # Context + Goal 결합하여 Planner에게 전달
    context_summary = state.get("context", "")
    trip_goal = state.get("trip_goal", {})
    
    combined_context = f"""
    [대화 요약] {context_summary}
    [여행 목표] {json.dumps(trip_goal, ensure_ascii=False)}
    """

    # planner.py 호출
    plan = planner.plan_tasks(combined_context, latest_user_msg)
    
    # 원본 메시지 저장 (Tools에서 사용)
    plan["original_user_message"] = latest_user_msg

    state["plan"] = plan
    return state


# ---------------------------------------------
# 4) 도구 실행 노드 (Tools -> Gemini)
# ---------------------------------------------
def tool_node(state: ChatState) -> ChatState:
    plan = state.get("plan", {})
    context = state.get("context", "")
    
    # tools.py 호출 (API 실행 + Gemini 답변 작성)
    answer = tools.run_tools_from_plan(plan, context)

    state["tool_output"] = answer
    
    # 대화 기록에 Assistant 메시지 추가
    state["messages"].append({"role": "assistant", "content": answer})

    return state