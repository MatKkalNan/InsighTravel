# main.py
import os
from typing import Optional, Dict, Any, List
from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel
from fastapi.staticfiles import StaticFiles
from pathlib import Path
from dotenv import load_dotenv

# [DB 관련]
from database import engine, SessionLocal
from models import Base

# [LangGraph 앱]
from graph_app import chat_graph_app
from graph_state import ChatState

# [날씨 모듈]
from weather_info import get_insight_weather_data

# [예약 기능]
from booking_page_service import booking_store

# [서비스 레이어]
from user_service import get_or_create_demo_user
from conversation_service import save_conversation_message
from session_service import load_latest_session_summary, upsert_session_summary
from trip_service import load_latest_trip, trip_to_state_payload, upsert_trip_from_state
from memory_service import (
    load_all_long_term_memories,
    extract_long_term_memory,
    save_long_term_memories,
)

load_dotenv()

ENABLE_DB_INIT = os.getenv("ENABLE_DB_INIT", "1") == "1"
DEMO_EXTERNAL_ID = "demo-user"
DEMO_SESSION_ID = "demo-session-1"


@asynccontextmanager
async def lifespan(app: FastAPI):
    if ENABLE_DB_INIT:
        Base.metadata.create_all(bind=engine)
        print("✅ DB 테이블 초기화 완료 (create_all)")
    else:
        print("ℹ️ DB 테이블 초기화 비활성화 (ENABLE_DB_INIT=0)")

    yield
    print("👋 Server shutdown complete")


app = FastAPI(title="Hybrid Travel Agent (OpenAI + Gemini)", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
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
    history: Optional[List[Dict[str, str]]] = []
    survey: Optional[Dict[str, str]] = None


class ChatResponse(BaseModel):
    reply: str
    plan: Dict[str, Any]
    trip_goal: Optional[Dict[str, Any]] = None


class BookingConfirmRequest(BaseModel):
    session_id: str
    booking_type: str
    item_index: int
    passenger_info: Dict[str, Any]


# 세션별 설문 결과 인메모리 저장 (세션 유지)
_survey_store: Dict[str, Dict[str, str]] = {}


class SurveyRequest(BaseModel):
    session_id: str
    answers: Dict[str, str]


@app.post("/survey")
async def save_survey(req: SurveyRequest):
    _survey_store[req.session_id] = req.answers
    return {"status": "ok"}


@app.get("/", response_class=HTMLResponse)
async def index():
    html_path = os.path.join(os.path.dirname(__file__), "chat.html")
    if os.path.exists(html_path):
        with open(html_path, "r", encoding="utf-8") as f:
            return HTMLResponse(f.read())
    return "<h1>Travel Agent Server is Running! ✈️</h1>"


@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    db = SessionLocal()
    try:
        # 1) demo user 보장
        demo_user = get_or_create_demo_user(
            db=db,
            external_id=DEMO_EXTERNAL_ID,
            name="Demo User",
        )
        user_id = demo_user.id
        session_id = DEMO_SESSION_ID

        # 2) preload
        loaded_summary = load_latest_session_summary(
            db=db,
            user_id=user_id,
            session_id=session_id,
        )

        loaded_trip = load_latest_trip(db=db, user_id=user_id)
        loaded_trip_goal, loaded_trip_profile, loaded_constraints = trip_to_state_payload(loaded_trip)

        loaded_long_term_memory = load_all_long_term_memories(
            db=db,
            user_id=user_id,
            limit=10,
        )

        # 3) 메시지 구성
        messages = list(request.history) if request.history else []
        messages.append({"role": "user", "content": request.message})

        # 4) user message 저장
        user_row = save_conversation_message(
            db=db,
            user_id=user_id,
            role="user",
            message=request.message,
        )

        # 설문 결과를 context 최상단에 강하게 주입
        survey_answers = request.survey or _survey_store.get(session_id, {})
        survey_prefix = ""
        if survey_answers:
            survey_prefix = (
                "[필수 적용 - 사용자 여행 성향 설문결과]\n"
                f"여행 분위기 선호: {survey_answers.get('atmosphere', '미정')}\n"
                f"예산 스타일: {survey_answers.get('budget', '미정')}\n"
                f"여행 우선순위: {survey_answers.get('priority', '미정')}\n"
                f"일정 스타일: {survey_answers.get('schedule', '미정')}\n"
                "위 설문 결과를 숙소/항공/식당/일정 추천 시 최우선으로 반드시 반영하세요.\n\n"
            )

        # 5) 날씨 데이터
        today_str = datetime.now().strftime("%Y-%m-%d")
        current_weather = get_insight_weather_data(37.5665, 126.9780, today_str)

        print(f"--- [DEBUG 1] API 호출 결과: {current_weather is not None} ---")
        if current_weather:
            print(f"--- [DEBUG 2] 데이터 샘플: {str(current_weather)[:100]}... ---")

        # 6) LangGraph 초기 상태
        initial_state: ChatState = {
            "user_id": user_id,
            "session_id": session_id,
            "messages": messages,
            "context": survey_prefix + (loaded_summary or request.context or ""),
            "short_memory_summary": loaded_summary or "",
            "trip_goal": loaded_trip_goal,
            "trip_profile": loaded_trip_profile,
            "constraints": loaded_constraints,
            "long_term_memory": loaded_long_term_memory,
            "plan": None,
            "tool_output": None,
            "tool_results": {},
            "replan": {"count": 0},
            "weather_data": current_weather,
        }

        # 7) 그래프 실행
        result = chat_graph_app.invoke(initial_state)

        print(f"DEBUG: 에이전트에게 전달된 날씨 데이터 -> {result.get('weather_data') is not None}")

        # 8) assistant message 저장
        assistant_reply = result.get("tool_output", "처리 중 오류가 발생했습니다.")
        assistant_row = save_conversation_message(
            db=db,
            user_id=user_id,
            role="assistant",
            message=assistant_reply,
        )

        # 9) 최신 summary 저장
        latest_context = result.get("context", "") or ""
        upsert_session_summary(
            db=db,
            user_id=user_id,
            session_id=session_id,
            summary=latest_context,
        )

        # 10) trip 상태 저장
        upsert_trip_from_state(
            db=db,
            user_id=user_id,
            state=result,
        )

        # 11) 장기 기억 추출 및 저장
        memory_payload = extract_long_term_memory(
            user_message=request.message,
            context=latest_context,
        )

        saved_count = save_long_term_memories(
            db=db,
            user_id=user_id,
            source_message_id=user_row.id,
            memory_payload=memory_payload,
        )
        print(f"✅ saved long-term memories: {saved_count}")

        return ChatResponse(
            reply=assistant_reply,
            plan=result.get("plan", {}) or {},
            trip_goal=result.get("trip_goal", {}) or {},
        )

    finally:
        db.close()


# -------------------------------------------------------------------
# [예약 기능] 가짜 예약 웹사이트 엔드포인트
# -------------------------------------------------------------------

@app.get("/booking/hotel", response_class=HTMLResponse)
async def booking_hotel_page(session_id: str = ""):
    html_path = os.path.join(os.path.dirname(__file__), "booking_hotel.html")
    with open(html_path, "r", encoding="utf-8") as f:
        return HTMLResponse(f.read())


@app.get("/booking/flight", response_class=HTMLResponse)
async def booking_flight_page(session_id: str = ""):
    html_path = os.path.join(os.path.dirname(__file__), "booking_flight.html")
    with open(html_path, "r", encoding="utf-8") as f:
        return HTMLResponse(f.read())


@app.get("/api/booking/data")
async def get_booking_data(session_id: str, type: str = "hotel"):
    data = booking_store.get_temp_data(session_id, type)
    return JSONResponse({"items": data, "session_id": session_id})


@app.post("/booking/confirm")
async def confirm_booking(req: BookingConfirmRequest):
    booking = booking_store.confirm_booking(
        req.session_id, req.booking_type, req.item_index, req.passenger_info
    )
    return JSONResponse(booking)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)