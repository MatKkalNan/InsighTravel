# graph_nodes.py
""" 
- 수정 (1) 2026-03-04, 요약 모델을 gpt-4-turbo에서 gpt-4o-mini로 변경
가격, 성능, latency 측면 우세 (gpt-ro-mini > gpt-4-turbo) 

- 수정 (2) 2026-03-04, 고정 포맷 변경
(기존)
context -> 3~5줄 요약
이 부분은 제약 조건(직항/예산/항공사/숙소 선호 등)을 빠뜨릴 확률 높음
(변경)
LLM이 요약을 항목별로 채우게 강제
(테스트 완료) 이상 x

""" 
import os
import json
from typing import Dict, Any

from dotenv import load_dotenv
from openai import OpenAI

from graph_state import ChatState
import planner
import tools
# [신규] 여행 목표 추출 서비스
from goal_service import extract_trip_goal_from_text

load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


# ---------------------------------------------
# 1) 컨텍스트 요약 노드 (OpenAI)
# ---------------------------------------------
def context_node(state: ChatState) -> ChatState:
    messages = state.get("messages", [])
    if not messages:
        return state

    # 최근 대화 6개 요약 / 롤링 컨텍스트 윈도우, long conversation -> recent messages + compressed summary
    last_msgs = messages[-6:]
    convo_text = "\n".join(f"{m['role']}: {m['content']}" for m in last_msgs)
    current_context = state.get("context", "")

    summary_prompt = f"""
    너는 여행 대화의 메모리 관리자다.
    아래 '이전 요약'과 '최근 대화'를 읽고, 반드시 지정한 형식으로만 업데이트된 요약을 작성하라.

    [이전 요약]
    {current_context}

    [최근 대화]
    {convo_text}

    [출력 형식 - 반드시 그대로]
    목적지: <도시/국가 또는 미정>
    기간: <YYYY-MM-DD ~ YYYY-MM-DD 또는 미정>
    박/일: <n박 m일 또는 미정>
    인원: <숫자 또는 미정>
    출발지: <도시 또는 미정>
    예산: <상한/범위/통화 또는 미정>
    항공 조건: <직항/경유/항공사 선호/제외/좌석 등급 등, 없으면 '없음'>
    숙소 조건: <동네/숙소타입/가격대/후기기준 등, 없으면 '없음'>
    일정/관심사: <핵심 일정/관심 키워드, 없으면 '없음'>
    확정된 결정: <확정된 내용만 bullet로, 없으면 '없음'>
    미해결 질문: <사용자에게 추가로 물어봐야 할 것, 없으면 '없음'>

    규칙:
    - 최근 대화에서 새로운 정보가 나오면 반영하고, 기존 정보와 충돌하면 '최근'을 우선한다.
    - 추측하지 말고, 텍스트에 없는 정보는 미정/없음으로 둔다.
    """

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