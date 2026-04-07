# main.py
'''
목적 : FastAPI 서버를 구성하고, /chat 요청을 받아 LangGraph 
파이프라인을 실행한 뒤 결과를 반환한다. 
(DB는 현재 테이블 생성만 수행하며 대화 저장/불러오기는 아직 
구현되지 않음)
대화 히스토리를 프론트엔드에서 전달받아 단기 메모리로 사용한다. 
추후 서비스 확장 시 DB 기반 장기 메모리로 전환 가능하도록 state 인터페이스는 유지한다

(+수정 2026.02.12. 최우진)

1. Base.metadata.create_all(bind=engine)

 - 기존: 모듈 import 시 실행

 - 변경: @app.on_event("startup")에서 실행
 -> import시 시작이 아니라 서버 시작시 실행으로 수정

2. messages = request.history ...

 - 기존: 원본 리스트를 직접 수정할 수 있음

 - 변경: list(request.history)로 복사 후 append
 -> 프론트에서 채팅 histroy 꼬일 위험 줄어듦

 3. DB 영향 범위 최소화

 -> DB의 발전 가능성은 남겨놓되 안정성 향상 
 <테스트 완료 - 오류 X>
'''
# main.py

import os
from typing import Optional, Dict, Any, List

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pathlib import Path
from pydantic import BaseModel
from dotenv import load_dotenv

# [DB 관련]
from database import engine
from models import Base

# [LangGraph 앱]
from graph_app import chat_graph_app
from graph_state import ChatState

# [날씨 모듈 통합]
from weather_info import get_insight_weather_data

# [예약 기능]
from booking_page_service import booking_store

load_dotenv()

# (선택) DB 초기화 on/off 토글: 문제가 생기면 환경변수로 끌 수 있음
# Windows PowerShell:  $env:ENABLE_DB_INIT="0"
# Mac/Linux:           export ENABLE_DB_INIT=0
ENABLE_DB_INIT = os.getenv("ENABLE_DB_INIT", "1") == "1"


@asynccontextmanager
async def lifespan(app: FastAPI):
    # ===== Startup =====
    if ENABLE_DB_INIT:
        Base.metadata.create_all(bind=engine)
        print("✅ DB 테이블 초기화 완료 (create_all)")
    else:
        print("ℹ️ DB 테이블 초기화 비활성화 (ENABLE_DB_INIT=0)")

    yield

    # ===== Shutdown =====
    # 필요 시 종료 처리(예: 리소스 정리) 추가
    print("👋 Server shutdown complete")


app = FastAPI(title="Hybrid Travel Agent (OpenAI + Gemini)", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 데모용: 운영이면 특정 origin만 허용 권장
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

BASE_DIR = Path(__file__).resolve().parent

# static 폴더의 절대 경로
STATIC_DIR = BASE_DIR / "static"

# 마운트
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


class ChatRequest(BaseModel):
    message: str
    context: Optional[str] = ""
    # 프론트엔드에서 이전 대화 기록을 넘겨줄 경우
    history: Optional[List[Dict[str, str]]] = []


class ChatResponse(BaseModel):
    reply: str
    plan: Dict[str, Any]
    trip_goal: Optional[Dict[str, Any]] = None


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
    # 1. 메세지 히스토리 정리
    # history 원본을 직접 수정하지 않도록 복사해서 사용 (중복/오염 방지)
    messages = list(request.history) if request.history else []
    messages.append({"role": "user", "content": request.message})
    
    # 2. 날씨 모듈 통합 (날씨 데이터를 가져와 변수에 저장) 
    from datetime import datetime
    today_str = datetime.now().strftime('%Y-%m-%d')
    
    current_weather = get_insight_weather_data(37.5665, 126.9780, today_str)
    # 현재는 서울(37.5665, 126.9780) 기준으로 호출
    # 추후 사용자의 목적지가 확정되면 해당 좌표를 동적으로 넣도록 개선필요
    
    print(f"--- [DEBUG 1] API 호출 결과: {current_weather is not None} ---")
    if current_weather:
        print(f"--- [DEBUG 2] 데이터 샘플: {str(current_weather)[:100]}... ---")
    
    # 3. LangGraph 초기 상태 설정

    initial_state: ChatState = {
        "messages": messages,
        "context": request.context or "",
        "trip_goal": None,
        "plan": None,
        "tool_output": None,
        "weather_data": current_weather, 
    }

    # 그래프 실행 (Start -> Context -> Goal -> Planner -> Tool -> End)
    result = chat_graph_app.invoke(initial_state)
    
    # [디버깅 추가] 에이전트에게 전달된 날씨 데이터가 실제로 있는지 확인
    print(f"DEBUG: 에이전트에게 전달된 날씨 데이터 -> {result.get('weather_data') is not None}")


    return ChatResponse(
        reply=result.get("tool_output", "처리 중 오류가 발생했습니다."),
        plan=result.get("plan", {}) or {},
        trip_goal=result.get("trip_goal", {}) or {},
    )


# -------------------------------------------------------------------
# [예약 기능] 가짜 예약 웹사이트 엔드포인트
# -------------------------------------------------------------------

class BookingConfirmRequest(BaseModel):
    session_id: str
    booking_type: str       # "hotel" or "flight"
    item_index: int
    passenger_info: Dict[str, Any]


@app.get("/booking/hotel", response_class=HTMLResponse)
async def booking_hotel_page(session_id: str = ""):
    """호텔 예약 페이지 (iframe으로 로드됨)"""
    html_path = os.path.join(os.path.dirname(__file__), "booking_hotel.html")
    with open(html_path, "r", encoding="utf-8") as f:
        return HTMLResponse(f.read())


@app.get("/booking/flight", response_class=HTMLResponse)
async def booking_flight_page(session_id: str = ""):
    """항공권 예약 페이지 (iframe으로 로드됨)"""
    html_path = os.path.join(os.path.dirname(__file__), "booking_flight.html")
    with open(html_path, "r", encoding="utf-8") as f:
        return HTMLResponse(f.read())


@app.get("/api/booking/data")
async def get_booking_data(session_id: str, type: str = "hotel"):
    """예약 페이지에서 호텔/항공편 데이터를 가져가는 API"""
    data = booking_store.get_temp_data(session_id, type)
    return JSONResponse({"items": data, "session_id": session_id})


@app.post("/booking/confirm")
async def confirm_booking(req: BookingConfirmRequest):
    """가짜 예약 확인 처리"""
    booking = booking_store.confirm_booking(
        req.session_id, req.booking_type,
        req.item_index, req.passenger_info
    )
    return JSONResponse(booking)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
