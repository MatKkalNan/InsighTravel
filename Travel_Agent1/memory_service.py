# memory_service.py
import json
from datetime import datetime
from sqlalchemy.orm import Session
from models import User, UserMemory


# -----------------------------------
# ① 최근 N개 대화 불러오기
# -----------------------------------
def get_recent_messages(db: Session, user: User, limit: int = 12) -> list:
    msgs = (
        db.query(UserMemory)
        .filter(UserMemory.user_id == user.id, UserMemory.mem_type == "chat")
        .order_by(UserMemory.created_at.desc())
        .limit(limit)
        .all()
    )
    return msgs[::-1]  # 오래된 → 최신 순으로 정렬


# -----------------------------------
# ② 대화 내용 저장
# -----------------------------------
def save_user_message(db: Session, user: User, role: str, content: str) -> None:
    msg = UserMemory(
        user_id=user.id,
        mem_type="chat",
        content=f"{role}: {content}",
    )
    db.add(msg)
    db.commit()


# -----------------------------------
# ③ TripGoal 메모리 읽기
# -----------------------------------
def get_trip_goal(db: Session, user: User) -> dict | None:
    """
    user의 최신 trip_goal(JSON)을 dict로 반환.
    """
    mem = (
        db.query(UserMemory)
        .filter(UserMemory.user_id == user.id, UserMemory.mem_type == "trip_goal")
        .order_by(UserMemory.created_at.desc())
        .first()
    )
    if not mem:
        return None

    try:
        return json.loads(mem.content)
    except Exception:
        return None


# -----------------------------------
# ④ TripGoal 메모리 저장
# -----------------------------------
def save_trip_goal(db: Session, user: User, goal: dict) -> None:
    """
    trip_goal JSON을 새로운 버전으로 저장 (이력 누적).
    """
    mem = UserMemory(
        user_id=user.id,
        mem_type="trip_goal",
        content=json.dumps(goal, ensure_ascii=False),
    )
    db.add(mem)
    db.commit()


# -----------------------------------
# ⑤ context 생성 (대화 + 목표 요약 포함 가능)
# -----------------------------------
def build_memory_context(db: Session, user: User, include_goal: bool = True) -> str:
    """
    planner와 tool에게 넘겨주는 context 생성.
    - 최근 대화
    - trip_goal 요약(선택)
    """
    msgs = get_recent_messages(db, user)
    lines = []

    for m in msgs:
        lines.append(m.content)

    # TripGoal 추가
    if include_goal:
        tg = get_trip_goal(db, user)
        if tg:
            lines.append("\n[TRIP_GOAL]")
            lines.append(json.dumps(tg, ensure_ascii=False))

    return "\n".join(lines)
