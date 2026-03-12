# models.py
"""
<코드 설명>
유저-대화 로그-유저 메모리(장기기억)을 DB로 표현한 모델
단기 메모리(대화) -> 장기 메모리(요약/선호)로 넘어가는 DB 설계

한 User는 여러 Conversation을 갖고
한 User는 여러 UserMemory를 갖고
하나의 UserMemory는 어떤 Conversation에서 추출됐는지를 
source_message_id로 연결할 수 있음(미완)

- users
- conversations (대화 로그)
- user_memories (대화에서 추출된 장기 메모리)

Agentic 관점에서의 장점
- 장기 메모리 분리 : 대화 로그와 메모리를 분리해서, planner가 필요한 메모리만 가져올 수 있음
- 근거 추적 가능 : memory가 어떤 conversation에서 생성됐는지 링크 가능
- 유저별 메모리
"""
from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True) # 내부 PK
    external_id = Column(String, unique=True, index=True, nullable=True) #외부 식별자 -> (데모용) 로그인 없이도 유저 식별 가능
    name = Column(String, nullable=True) # 표시용 이름

    conversations = relationship("Conversation", back_populates="user")
    memories = relationship("UserMemory", back_populates="user")

class Conversation(Base):
    __tablename__ = "conversations"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False) # user.id FK

    role = Column(String(20), nullable=False)  # 'user' or 'assistant'
    message = Column(Text, nullable=False) # 대화 텍스트
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False) # 생성 시각

    user = relationship("User", back_populates="conversations")
    generated_memories = relationship("UserMemory", back_populates="source_message")
    
class UserMemory(Base):
    __tablename__ = "user_memories"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False) # user.id FK

    # ex) profile, health_condition, medication_pattern, mood_pattern, preference_hobby, guardian, interaction_style ...
    type = Column(String(50), nullable=False) #메모리 종류

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

