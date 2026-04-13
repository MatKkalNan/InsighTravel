# main.py
import os
import json
from typing import Optional, Dict, Any, List
from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel
from fastapi.staticfiles import StaticFiles
from pathlib import Path
from dotenv import load_dotenv

# [DB 관련]
from database import engine, SessionLocal, get_db
from models import Base
from sqlalchemy.orm import Session
from models import BookingHistory, CancelledBookingHistory

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
from survey_service import save_survey, get_survey

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
STATIC_DIR = BASE_DIR / "static"
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


class ChatRequest(BaseModel):
    message: str
    session_id: Optional[str] = None
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


class SurveyRequest(BaseModel):
    session_id: str
    answers: Dict[str, str]


@app.post("/survey")
async def save_survey_endpoint(req: SurveyRequest):
    save_survey(session_id=req.session_id, answers=req.answers)
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
        demo_user = get_or_create_demo_user(
            db=db,
            external_id=DEMO_EXTERNAL_ID,
            name="Demo User",
        )
        user_id = demo_user.id
        session_id = request.session_id or DEMO_SESSION_ID

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

        messages = list(request.history) if request.history else []
        messages.append({"role": "user", "content": request.message})

        user_row = save_conversation_message(
            db=db,
            user_id=user_id,
            role="user",
            message=request.message,
        )

        survey_answers = request.survey or get_survey(session_id)
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

        today_str = datetime.now().strftime("%Y-%m-%d")
        current_weather = get_insight_weather_data(37.5665, 126.9780, today_str)

        print(f"--- [DEBUG 1] API 호출 결과: {current_weather is not None} ---")
        if current_weather:
            print(f"--- [DEBUG 2] 데이터 샘플: {str(current_weather)[:100]}... ---")

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
            "survey": survey_answers or None,
        }

        result = chat_graph_app.invoke(initial_state)

        print(f"DEBUG: 에이전트에게 전달된 날씨 데이터 -> {result.get('weather_data') is not None}")

        assistant_reply = result.get("tool_output", "처리 중 오류가 발생했습니다.")
        assistant_row = save_conversation_message(
            db=db,
            user_id=user_id,
            role="assistant",
            message=assistant_reply,
        )

        latest_context = result.get("context", "") or ""
        upsert_session_summary(
            db=db,
            user_id=user_id,
            session_id=session_id,
            summary=latest_context,
        )

        upsert_trip_from_state(
            db=db,
            user_id=user_id,
            state=result,
        )

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
async def confirm_booking(payload: dict, db: Session = Depends(get_db)):
    session_id = payload.get("session_id", "demo-session-1")
    booking_type = payload.get("booking_type", "flight")
    item_index = payload.get("item_index", 0)
    passenger_info = payload.get("passenger_info", {})

    print("[DEBUG] confirm API payload:", payload)

    result = booking_store.confirm_booking(
        session_id=session_id,
        booking_type=booking_type,
        item_index=item_index,
        passenger_info=passenger_info,
        db=db,
    )

    print("[DEBUG] DB 전달됨?", db is not None)
    return JSONResponse(result)


@app.get("/booking/history", response_class=HTMLResponse)
async def booking_history_page():
    html_path = os.path.join(os.path.dirname(__file__), "booking_history.html")
    with open(html_path, "r", encoding="utf-8") as f:
        return HTMLResponse(content=f.read())


@app.get("/api/bookings")
def get_bookings(db: Session = Depends(get_db)):
    session_id = "demo-session-1"  # 🔥 고정

    rows = db.query(BookingHistory).filter(
        BookingHistory.session_id == session_id
    ).order_by(BookingHistory.created_at.desc()).all()

    return {
        "items": [
            {
                "booking_code": r.booking_code,
                "type": r.booking_type,
                "status": r.status,
                "title": r.title,
                "destination": r.destination,
                "start_date": r.start_date,
                "end_date": r.end_date,
                "payload": json.loads(r.payload_json or "{}")
            }
            for r in rows
        ]
    }


@app.post("/api/bookings/{booking_code}/cancel")
def cancel_booking(booking_code: str, db: Session = Depends(get_db)):
    booking = (
        db.query(BookingHistory)
        .filter(BookingHistory.booking_code == booking_code)
        .first()
    )

    if not booking:
        return JSONResponse(
            status_code=404,
            content={"ok": False, "message": "예약 내역을 찾을 수 없습니다."}
        )

    cancelled = CancelledBookingHistory(
        user_id=booking.user_id,
        session_id=booking.session_id,
        booking_type=booking.booking_type,
        booking_code=booking.booking_code,
        title=booking.title,
        destination=booking.destination,
        start_date=booking.start_date,
        end_date=booking.end_date,
        payload_json=booking.payload_json,
        original_created_at=booking.created_at,
    )

    db.add(cancelled)
    db.delete(booking)
    db.commit()

    return {
        "ok": True,
        "message": "예약이 취소되었습니다.",
        "booking_code": booking_code,
    }

@app.get("/api/cancelled-bookings")
def get_cancelled_booking_history(db: Session = Depends(get_db)):
    session_id = "demo-session-1"

    bookings = (
        db.query(CancelledBookingHistory)
        .filter(CancelledBookingHistory.session_id == session_id)
        .order_by(CancelledBookingHistory.cancelled_at.desc())
        .all()
    )

    items = []
    for b in bookings:
        try:
            payload = json.loads(b.payload_json) if b.payload_json else {}
        except Exception as e:
            print("[DEBUG] cancelled payload_json parse error:", e)
            payload = {}

        items.append({
            "booking_code": b.booking_code,
            "booking_type": b.booking_type,
            "status": "cancelled",
            "title": b.title,
            "destination": b.destination,
            "start_date": b.start_date,
            "end_date": b.end_date,
            "created_at": b.cancelled_at.isoformat() if b.cancelled_at else None,
            "payload": payload,
        })

    return {"items": items}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)