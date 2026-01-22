# services.py
from sqlalchemy.orm import Session
from typing import List

from models import User, Conversation


def get_or_create_user(db: Session, external_id: str) -> User:
    """외부 user_id(예: demo-user)로 User 레코드를 찾고, 없으면 생성."""
    user = db.query(User).filter(User.external_id == external_id).first()
    if not user:
        user = User(external_id=external_id, name="Demo User")
        db.add(user)
        db.commit()
        db.refresh(user)
    return user


def get_recent_context(db: Session, user: User, limit: int = 20, max_chars: int = 2000) -> str:
    rows = (
        db.query(Conversation)
        .filter(Conversation.user_id == user.id)
        .order_by(Conversation.id.desc())
        .limit(limit)
        .all()
    )
    rows.reverse()
    lines = []
    total = 0
    for c in rows:
        line = f"{c.role}: {c.message}"
        total += len(line)
        if total > max_chars:
            break
        lines.append(line)
    return "\n".join(lines)

