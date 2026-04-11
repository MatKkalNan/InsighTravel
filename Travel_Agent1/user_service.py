from sqlalchemy.orm import Session
from models import User

def get_or_create_demo_user(db: Session, external_id: str, name: str = "Demo User") -> User:
    user = db.query(User).filter(User.external_id == external_id).first()
    if user:
        return user

    user = User(external_id=external_id, name=name)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user