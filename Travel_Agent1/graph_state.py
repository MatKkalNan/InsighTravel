# graph_state.py
from typing import TypedDict, List, Literal, Optional, Dict, Any


class ChatMessage(TypedDict):
    role: Literal["user", "assistant"]
    content: str


class ChatState(TypedDict):
    """
    여행 에이전트용 LangGraph 상태 정의.

    - messages: 지금까지의 대화 로그
    - context: 플래너/툴에 넘길 요약 컨텍스트 (최근 대화 요약 등)
    - trip_goal: 사용자가 준비 중인 '여행 장기 목표' 요약
      예: "3월에 친구랑 3박 4일 오사카, 예산 80만 원 정도"
    - plan: planner.plan_tasks() 결과(JSON)
    - tool_output: tools.run_tools_from_plan() 결과(최종 답변 텍스트)
    """
    messages: List[ChatMessage]
    context: str
    trip_goal: Optional[str]
    plan: Optional[Dict[str, Any]]
    tool_output: Optional[str]
