# main.py
import os
from typing import Optional, Dict, Any, List

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from dotenv import load_dotenv

# [DB 관련]
from database import engine
from models import Base

from planner import plan_tasks
from tools import run_tools_from_plan

# [LangGraph 앱]
from graph_app import chat_graph_app
from graph_state import ChatState

load_dotenv()

# 1. 앱 시작 시 DB 테이블 자동 생성 (없으면 생성)
Base.metadata.create_all(bind=engine)

app = FastAPI(title="Hybrid Travel Agent (OpenAI + Gemini)")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class ChatRequest(BaseModel):
    session_id: Optional[str] = None
    message: str
    context: Optional[str] = ""
    # 프론트엔드에서 이전 대화 기록을 넘겨줄 경우
    history: Optional[List[Dict[str, str]]] = []

class ChatResponse(BaseModel):
    reply: str # 에이전트 최종 답변
    plan: Dict[str, Any] # planner가 만든 계획
    trip_goal: Optional[Dict[str, Any]] = None
    route: str # 사용된 주요 tool 이름

@app.get("/", response_class=HTMLResponse)
async def index():
    # 간단한 테스트용 UI가 있다면 로드, 없으면 텍스트 반환
    html_path = os.path.join(os.path.dirname(__file__), "chat.html")
    if os.path.exists(html_path):
        with open(html_path, "r", encoding="utf-8") as f:
            return HTMLResponse(f.read())
    return "<h1>Travel Agent Server is Running! ✈️</h1>"

@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    # 2. LangGraph 초기 상태 설정
    # history가 있으면 가져오고, 없으면 현재 메시지만 추가
    messages = request.history if request.history else []
    messages.append({"role": "user", "content": request.message})

    initial_state: ChatState = {
        "messages": messages,
        "context": request.context or "",
        "trip_goal": None,
        "plan": None,
        "tool_output": None
    }

    # 3. 그래프 실행 (Start -> Context -> Goal -> Planner -> Tool -> End)
    # invoke()가 그래프의 전체 흐름을 실행합니다.
    result = chat_graph_app.invoke(initial_state)

    # 4. 결과 반환
    # tool_output은 Gemini가 최종적으로 작성한 답변입니다.
    return ChatResponse(
        reply=result.get("tool_output", "처리 중 오류가 발생했습니다."),
        plan=result.get("plan", {}),
        trip_goal=result.get("trip_goal", {})
    )

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)