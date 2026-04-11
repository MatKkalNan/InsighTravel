# graph_app.py
from langgraph.graph import StateGraph, START, END
from graph_state import ChatState

# 수정된 graph_nodes에서 필요한 노드만 가져옴
from graph_nodes import (
    context_node,
    goal_node,
    planner_node,
    memory_gate_node,
    tool_node
)

def build_chat_graph():
    # 1. 그래프 초기화
    workflow = StateGraph(ChatState)

    # 2. 노드 등록
    workflow.add_node("context_node", context_node)   # 대화 요약
    workflow.add_node("goal_node", goal_node)         # 여행 목표 추출
    workflow.add_node("planner_node", planner_node)
    workflow.add_node("memory_gate_node", memory_gate_node)    # 계획 수립
    workflow.add_node("tool_node", tool_node)         # 도구 실행 및 답변

    # 3. 엣지(Edge) 연결 - 선형 구조
    # 시작 -> 요약
    workflow.add_edge(START, "context_node")
    
    # 요약 -> 목표 추출
    workflow.add_edge("context_node", "goal_node")
    
    # 목표 추출 -> 플래너
    workflow.add_edge("goal_node", "planner_node")
    
    # 플래너 -> 도구 실행
    workflow.add_edge("planner_node", "memory_gate_node")

    workflow.add_edge("memory_gate_node", "tool_node")
    
    # 도구 실행 -> 종료
    workflow.add_edge("tool_node", END)

    return workflow.compile()

# 실행 가능한 앱 객체
chat_graph_app = build_chat_graph()
