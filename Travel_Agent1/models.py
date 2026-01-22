# models.py
from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    external_id = Column(String, unique=True, index=True, nullable=True)
    name = Column(String, nullable=True)

    conversations = relationship("Conversation", back_populates="user")
    memories = relationship("UserMemory", back_populates="user")

class Conversation(Base):
    __tablename__ = "conversations"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)

    role = Column(String(20), nullable=False)  # 'user' or 'assistant'
    message = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    user = relationship("User", back_populates="conversations")
    generated_memories = relationship("UserMemory", back_populates="source_message")
    
class UserMemory(Base):
    __tablename__ = "user_memories"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)

    # ex) profile, health_condition, medication_pattern, mood_pattern, preference_hobby, guardian, interaction_style ...
    type = Column(String(50), nullable=False)

    # 사람이 읽을 수 있는 한 줄 요약
    content = Column(Text, nullable=False)

    # 1~5: 중요도 (5가 가장 중요)
    importance = Column(Integer, default=3, nullable=False)

    # 이 메모리가 어떤 대화 메시지에서 추출됐는지 (없어도 됨)
    source_message_id = Column(Integer, ForeignKey("conversations.id"), nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # 관계 설정
    user = relationship("User", back_populates="memories")
    source_message = relationship("Conversation", back_populates="generated_memories")

