# survey_service.py
"""
목적: 채팅(세션)별 설문 결과를 저장·조회·삭제하는 서비스 레이어.

현재는 인메모리 딕셔너리로 관리하며, 서버 재시작 시 초기화된다.
추후 DB 연동 시 이 파일의 함수 내부만 수정하면 main.py 등 호출부는 변경 불필요.

저장 구조:
    _survey_store: Dict[session_id, answers]
    answers: {
        "atmosphere": str,  # 여행 분위기 선호
        "budget":     str,  # 예산 스타일
        "priority":   str,  # 여행 우선순위
        "schedule":   str,  # 일정 스타일
    }
"""

from typing import Dict, Optional

# 세션별 설문 결과 인메모리 저장소
_survey_store: Dict[str, Dict[str, str]] = {}


def save_survey(session_id: str, answers: Dict[str, str]) -> None:
    """
    세션의 설문 결과를 저장한다.
    같은 session_id로 다시 저장하면 덮어쓴다.
    """
    if not session_id or not session_id.strip():
        raise ValueError("session_id must not be empty")
    if not answers:
        raise ValueError("answers must not be empty")

    _survey_store[session_id.strip()] = answers


def get_survey(session_id: str) -> Optional[Dict[str, str]]:
    """
    session_id에 해당하는 설문 결과를 반환한다.
    해당 세션의 설문 결과가 없으면 None을 반환한다.
    """
    if not session_id or not session_id.strip():
        return None

    return _survey_store.get(session_id.strip())


def delete_survey(session_id: str) -> None:
    """
    세션의 설문 결과를 삭제한다.
    새 채팅 시작 시 이전 세션 데이터 정리 용도.
    해당 session_id가 없어도 오류 없이 무시한다.
    """
    _survey_store.pop(session_id.strip(), None)