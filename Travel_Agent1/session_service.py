from sqlalchemy.orm import Session
from models import SessionMemory


def upsert_session_summary(
    db: Session,
    user_id: int,
    session_id: str,
    summary: str,
) -> SessionMemory:
    if not session_id or not session_id.strip():
        raise ValueError("session_id must not be empty")

    if summary is None:
        raise ValueError("summary must not be None")

    session_id = session_id.strip()
    summary = summary.strip()

    try:
        row = (
            db.query(SessionMemory)
            .filter(
                SessionMemory.user_id == user_id,
                SessionMemory.session_id == session_id,
            )
            .first()
        )

        if row:
            row.summary = summary
        else:
            row = SessionMemory(
                user_id=user_id,
                session_id=session_id,
                summary=summary,
            )
            db.add(row)

        db.commit()
        db.refresh(row)
        return row

    except Exception:
        db.rollback()
        raise


def load_latest_session_summary(
    db: Session,
    user_id: int,
    session_id: str,
) -> str:
    if not session_id or not session_id.strip():
        return ""

    row = (
        db.query(SessionMemory)
        .filter(
            SessionMemory.user_id == user_id,
            SessionMemory.session_id == session_id.strip(),
        )
        .first()
    )

    return row.summary if row and row.summary else ""