# database.py
"""
목적: SQLAlchemy로 SQLite DB에 연결하기 위한 엔진과 세션 팩토리(SessionLocal)를 구성한다.
SQLALCHEMY_DATABASE_URL은 SQLite 파일 기반 DB의 연결 문자열이다.
create_engine()은 DB와 통신할 엔진을 생성하며, connect_args={"check_same_thread": False}는 
SQLite의 “같은 스레드에서만 사용” 제약을 완화해 웹 서버 환경에서의 사용을 가능하게 한다.(FastAPI 오류 방지)
SessionLocal = sessionmaker(...)는 엔진에 바인딩된 세션 팩토리로, 요청 단위로 세션을 
생성해 트랜잭션(commit/rollback)과 ORM 객체 상태 추적을 담당한다.
(요약)
main.py에 engine 제공
SessionLocal 세션 팩토리 제공
"""
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./app.db")

connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}

engine = create_engine(
    DATABASE_URL,
    connect_args=connect_args,
    pool_pre_ping=True,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
