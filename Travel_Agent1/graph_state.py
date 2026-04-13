# graph_state.py
from typing import TypedDict, List, Literal, Optional, Dict, Any


class ChatMessage(TypedDict):
    role: Literal["user", "assistant"]
    content: str


class TripGoal(TypedDict, total=False):
    destination: str
    nights: int
    days: int
    month: str
    budget_krw: int
    style_tags: List[str]
    status: str


class TripProfile(TypedDict, total=False):
    destination: str   # ex) "Tokyo"
    start_date: str    # ex) "2026-03-02"
    end_date: str      # ex) "2026-03-05"
    nights: int        # ex) 3
    days: int          # ex) 4
    travelers: int     # ex) 2
    departure_city: str  # ex) "Seoul"


class Constraints(TypedDict, total=False):
    hard: Dict[str, Any]
    soft: Dict[str, Any]


class ToolResult(TypedDict, total=False):
    status: Literal["ok", "no_result", "error"]
    data: Any
    evidence: Optional[Dict[str, Any]]
    retry_hint: Optional[str]


class ReplanState(TypedDict, total=False):
    count: int
    reason: Optional[str]
    last_adjustment: Optional[Dict[str, Any]]


class ChatState(TypedDict, total=False):
    """
    여행 에이전트용 LangGraph 상태 정의
    """

    user_id: Optional[int]
    session_id: Optional[str]

    messages: List[ChatMessage]
    context: str
    short_memory_summary: Optional[str]
    long_term_memory: Optional[Dict[str, Any]]

    trip_goal: Optional[TripGoal]
    trip_profile: Optional[TripProfile]
    constraints: Optional[Constraints]

    plan: Optional[Dict[str, Any]]
    tool_output: Optional[str]
    tool_results: Optional[Dict[str, ToolResult]]
    replan: Optional[ReplanState]

    weather_data: Optional[Dict[str, Any]]
    survey: Optional[Dict[str, str]]