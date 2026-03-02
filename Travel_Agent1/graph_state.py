# graph_state.py
from typing import TypedDict, List, Literal, Optional, Dict, Any


class ChatMessage(TypedDict):
    role: Literal["user", "assistant"]
    content: str

class TripProfile(TypedDict, total = False):
    destination: str # ex) "Tokyo"
    start_date: str # ex) "2026-03-02"
    end_date: str # ex) "2026-03-05"
    nights: int # ex) "3"
    days: int # ex) 4
    travelers: int # ex) "2"(people)
    departure_city: str # ex) "Seoul"

class Constraints(TypedDict, total = False):
    hard: Dict[str, Any] # hard_constraint
    # ex) budget_upper, date
    soft: Dict[str, Any] # soft_constraint
    # user_prefer ex) 가성비/luxury...

class ToolResult(TypedDict, total = False):
    status: Literal["ok", "no_result", "error"]
    data: Any
    evidence: Optional[Dict[str, Any]] # reference/search_option/link
    retry_hint: Optional[str] # hint for retry (relax conditions...)

class ReplanState(TypedDict, total = False):
    count: int # replan count
    reason: Optional[str] # reason for replan
    last_adjustment: Optional[Dict[str, Any]] # change what & how


class ChatState(TypedDict):
    """
    여행 에이전트용 LangGraph 상태 정의.

    - messages: 지금까지의 대화 로그
    - context: 플래너/툴에 넘길 요약 컨텍스트 (최근 대화 요약 등)
    - trip_goal: 사용자가 준비 중인 '여행 장기 목표' 요약
      예: "3월에 친구랑 3박 4일 오사카, 예산 80만 원 정도"
    - plan: planner.plan_tasks() 결과(JSON)
    - tool_output: tools.run_tools_from_plan() 결과(최종 답변 텍스트)

    (+추가 2026-03-02)
    Agentic AI로의 발전을 위한 state 수정
    - trip_profile: 유저 여행 계획 세부 기억
    - constraints: 조건 누적 + 부정 조건 처리
    - tool_results + replan: "시도/결과/재계획" 기록 -> 루프/리플래닝 기능
    
    [근거 있는 판단 가능]
    아직은 chat_state만 수정, 후에 다른 코드 수정을 통해 발전 가능
    (2026/03/02 수정 후 테스트 완료 : 오류 x)
    """
    # 기존
    messages: List[ChatMessage]
    context: str
    trip_goal: Optional[str] # trip_goal: Optional[Dict[str, Any]]
    plan: Optional[Dict[str, Any]]
    tool_output: Optional[str]

    # 추가
    trip_profile: Optional[TripProfile]
    constraints: Optional[Constraints]
    tool_results: Optional[Dict[str, ToolResult]]
    replan: Optional[ReplanState]

