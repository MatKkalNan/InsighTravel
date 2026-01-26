# prompts/goal_prompts.py
import json
from typing import Optional

GOAL_EXTRACTION_SYSTEM = """
당신은 대화 내용을 분석하여 '사용자의 여행 목표'를 데이터로 추출하는 분석기입니다.
창작하지 말고, 대화에서 확인된 사실만 JSON으로 정리하세요.
"""

def get_goal_extraction_user_prompt(user_message: str, context: str, previous_goal: Optional[dict]) -> str:
    prev_goal_json = json.dumps(previous_goal, ensure_ascii=False) if previous_goal is not None else "null"
    
    return f"""
    [대화 흐름]
    {context}

    [최근 사용자 발화]
    {user_message}

    [기존 목표 데이터]
    {prev_goal_json}

    [지시사항]
    1. 위 내용을 종합하여 현재 사용자가 계획 중인 '대표 여행' 정보를 JSON으로 갱신하세요.
    2. 여행과 무관한 잡담은 무시하세요.
    3. JSON 필드: destination, nights, days, month, budget_krw, style_tags, status
    4. 오직 JSON 문자열만 출력하세요.
    """