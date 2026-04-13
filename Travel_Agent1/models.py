# models.py
from datetime import datetime

from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, JSON
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from database import Base

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    external_id = Column(String, unique=True, index=True, nullable=True)
    name = Column(String, nullable=True)

    conversations = relationship("Conversation", back_populates="user", cascade="all, delete-orphan")
    memories = relationship("UserMemory", back_populates="user", cascade="all, delete-orphan")
    trips = relationship("Trip", back_populates="user", cascade="all, delete-orphan")
    session_memories = relationship("SessionMemory", back_populates="user", cascade="all, delete-orphan")


class Conversation(Base):
    __tablename__ = "conversations"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)

    role = Column(String(20), nullable=False)   # "user" / "assistant"
    message = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    user = relationship("User", back_populates="conversations")
    generated_memories = relationship("UserMemory", back_populates="source_message")


class UserMemory(Base):
    __tablename__ = "user_memories"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)

    # 예: "preference", "profile", "travel_style", "budget_preference" 등
    memory_type = Column(String(50), nullable=False)

    # 사람이 읽을 수 있는 요약 텍스트
    content = Column(Text, nullable=False)

    # 1~5 중요도
    importance = Column(Integer, default=3, nullable=False)

    # 어떤 대화 메시지에서 추출됐는지
    source_message_id = Column(Integer, ForeignKey("conversations.id"), nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    user = relationship("User", back_populates="memories")
    source_message = relationship("Conversation", back_populates="generated_memories")


class SessionMemory(Base):
    __tablename__ = "session_memories"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)

    # 데모 단계에서는 세션을 문자열 하나로 식별
    session_id = Column(String, index=True, nullable=False)

    # context_node가 만든 최신 요약
    summary = Column(Text, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    user = relationship("User", back_populates="session_memories")


class Trip(Base):
    __tablename__ = "trips"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)

    destination = Column(String, nullable=True)
    start_date = Column(String, nullable=True)
    end_date = Column(String, nullable=True)
    nights = Column(Integer, nullable=True)
    days = Column(Integer, nullable=True)
    travelers = Column(Integer, nullable=True)
    departure_city = Column(String, nullable=True)

    # goal_service 결과 저장
    trip_goal_json = Column(JSON, nullable=True)

    # constraint 누적 결과 저장
    constraints_json = Column(JSON, nullable=True)

    # 예: just_started / choosing_city / planning_itinerary / done
    status = Column(String(50), nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    user = relationship("User", back_populates="trips")

class BookingHistory(Base):
    __tablename__ = "booking_history"

    id = Column(Integer, primary_key=True, index=True)

    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    session_id = Column(String, nullable=False, index=True)

    booking_type = Column(String, nullable=False)
    booking_code = Column(String, unique=True, index=True, nullable=False)

    status = Column(String, default="confirmed")

    title = Column(String, nullable=True)
    destination = Column(String, nullable=True)

    start_date = Column(String, nullable=True)
    end_date = Column(String, nullable=True)

    payload_json = Column(Text, nullable=False)

    created_at = Column(DateTime(timezone=True), server_default=func.now())

class CancelledBookingHistory(Base):
    __tablename__ = "cancelled_booking_history"

    id = Column(Integer, primary_key=True, index=True)

    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    session_id = Column(String, nullable=False, index=True)

    booking_type = Column(String, nullable=False)
    booking_code = Column(String, index=True, nullable=False)

    title = Column(String, nullable=True)
    destination = Column(String, nullable=True)

    start_date = Column(String, nullable=True)
    end_date = Column(String, nullable=True)

    payload_json = Column(Text, nullable=False)

    original_created_at = Column(DateTime(timezone=True), nullable=True)
    cancelled_at = Column(DateTime(timezone=True), server_default=func.now())