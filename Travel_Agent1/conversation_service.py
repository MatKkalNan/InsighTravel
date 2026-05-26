from sqlalchemy.orm import Session
from models import Conversation


def save_conversation_message(
    db: Session,
    user_id: int,
    role: str,
    message: str,
) -> Conversation:
    if role not in {"user", "assistant", "system"}:
        role = "user"

    if not message or not message.strip():
        raise ValueError("message must not be empty")

    conv = Conversation(
        user_id=user_id,
        role=role,
        message=message.strip(),
    )

    try:
        db.add(conv)
        db.commit()
        db.refresh(conv)
        return conv
    except Exception:
        db.rollback()
        raise

def load_recent_conversations(
    db: Session,
    user_id: int,
    limit: int = 10,
):
    rows = (
        db.query(Conversation)
        .filter(Conversation.user_id == user_id)
        .order_by(Conversation.created_at.desc())
        .limit(limit)
        .all()
    )

    rows = list(reversed(rows))

    return [
        {
            "role": row.role,
            "content": row.message,
        }
        for row in rows
    ]