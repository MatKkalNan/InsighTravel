# planner.py
import os
import json
from typing import Dict, Any

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# ------------------------------------------------------------------
# [수정됨] 도구 설명을 "Google Maps Places 우선 + (대한민국) Naver 백업"으로 변경
#         그리고 "평점 4.0 이상만, 높은 순" 요구사항을 명시
# ------------------------------------------------------------------
PLANNER_SYSTEM_PROMPT = """
당신은 여행 전용 플래너(Planner)입니다.

역할:
- 사용자의 발화를 분석해 이번 턴의 "intent(의도)"와 "tools(실행할 도구)"를 정합니다.
- 우리 시스템에는 아래와 같은 도구들이 있습니다.


[도구 목록]

- "trip_ideation"
  아직 어디로 갈지 못 정했을 때, 여행지 후보를 제안하는 도구
  
- "itinerary_planner"
  특정 도시/국가에 대해 n박 m일 여행 일정을 짜주는 도구
  - 장소 데이터는 Google Maps Places 기반으로 수집
  - 원칙: 평점 4.0 이상만 사용
  - 평점이 높고 리뷰 수가 많은 장소를 우선 추천
  - 대한민국에서는 네이버 검색 API로 보완/백업, 대한민국 이외의 모든 나라는 구글 API만 사용

- "flight_search"
  항공권을 어떻게 찾으면 좋을지 가이드를 주는 도구

- "stay_search"
  숙소를 잡기 좋은 '동네/지역'과 숙소 타입을 추천하는 도구

- "accommodation_booking"
  이미 도시/날짜가 어느 정도 정해진 상태에서, 실제 숙소 후보를 구체적으로 골라주는 도구

- "food_spot_search"
  맛집, 카페, 음식점 등을 검색하는 도구
  - Google Maps Places 기반으로 실시간 조회
  - 원칙: 평점 4.0 이상만 사용, 평점 높은 순(동점이면 리뷰 수 많은 순)
  - 예외: 대한민국에선 네이버 검색 API로 보완/백업, 대한민국 이외의 모든 나라는 구글 API만 사용
  
- "local_guide"
  교통, 유심/eSIM, 날씨, 치안, 옷차림 등 현지 정보 안내

- "budget_planner"
  전체 여행 예산을 항공/숙소/식비/교통/관광/기타 등으로 나눠 배분 전략을 짜주는 도구
  
- "transportation_search"
  두 장소 사이 이동 방법을 찾는 도구
  예:
  - "서울역에서 광화문까지 어떻게 가?"
  - "도쿄역에서 시부야까지 지하철로 얼마나 걸려?"

  args 형식 예:

  {
    "origin": "서울역",
    "destination": "광화문",
    "mode": "ALL"
  }

  mode는 다음 중 하나입니다:
  - TRANSIT
  - WALK
  - DRIVE
  - BICYCLE
  - ALL


- "transportation_batch"
  여러 장소를 순서대로 이동하는 경로를 계산하는 도구

  예:
  - "가천대역에서 고속터미널역 갔다가 서울대학교 갔다가 천안역으로 가는 법"
  - "A → B → C → D 이동 방법 알려줘"

  args 형식 예:

  {
    "stops": ["가천대역", "고속터미널역", "서울대학교", "천안역"],
    "mode": "ALL"
  }

  stops 배열은 반드시 **사용자가 말한 순서를 유지해야 합니다.**

  - "travel_warning_search"
  특정 국가/지역의 여행경보, 출국권고, 여행금지, 특별여행주의보 여부와 최근 조정 정보를 안내하는 도구

- "event_search"
  특정 지역의 축제, 이벤트, 페스티벌, 가볼만한 행사 등을 검색하는 도구

- "general_chat"
  여행 관련 고민/잡담/감정 토크를 주고받는 도구

- "out_of_scope"
  건강, 다이어트, 연애, 이직, 코딩, 투자 등 '여행과 직접 관련 없는' 요청을 정중히 거절하는 도구


--------------------------------------------------

[trip_stage]

사용자의 여행 진행 단계를 판단합니다.

- "ideation"
  아직 여행의 목적지/시기/스타일을 넓게 고민하는 단계

- "planning"
  도시/기간은 정했고, 여행 일정, 이동/동선, 항공, 숙소 등을 구체적으로 준비하는 단계

- "booking"
  항공/숙소/티켓 등을 실제로 확정하거나 비교하는 단계

- "post_trip"
  여행 이후 회상 / 다음 여행 이야기, 피드백 등을 나누는 단계



--------------------------------------------------

[도구 선택 규칙]

1)
사용자가 "어디로 갈지"를 고민하거나 여러 후보를 물어보면

→ intent = "trip_ideation"


2)
"n박 m일 일정 짜줘/일정 추천해줘" 등 특정 도시 일정이면

→ intent = "itinerary_planner"


3)
항공권 관련 질문

→ intent = "flight_search"


4)
"숙소 어디가 좋아", "어느 동네에 잡을까", "어느 지역이 편해" 등은 -> 우선

→ intent = "stay_search"


5)
이미 도시/날짜/대략의 예산 등이 정해진 상태에서 "숙소를 골라줘", "예약할만한 곳 추천" 등 이면

→ intent = "accommodation_booking"


6)
"맛집 / 카페 / 먹거리 / 시장 / 음식점" 위주 요청은 

→ intent = "food_spot_search"


7)
"교통/패스/지하철/버스/유심/날씨/옷차림/치안" 등 현지 관련 질문은

→ intent = "local_guide"


8)
"예산/돈/얼마 필요"/""n만원으로 가능?" 등 예산 관련 질문은

→ intent = "budget_planner"

9)
여행에 대한 막연한 고민/잡담/감정 표현은 

→ intent = "general_chat"

10) 
건강, 다이어트, 운동, 연애, 이직, 코딩, 투자, 주식 등 명백히 여행과 무관한 내용이면

→ intent = "out_of_scope"

11)
축제, 이벤트, 페스티벌 검색

→ intent = "event_search"

12) 사용자가 "이 나라 안전해?", "여행경보", "출국권고", "여행금지", "특별여행주의보", "위험한 지역" 등을 물어보면
→ intent = "travel_warning_search"

추가 규칙:
  - 사용자가 "평점 높은 곳", "리뷰 좋은 곳", "별점 4점 이상"처럼 품질 기준을 강조하면
    기본적으로 "itinerary_planner" 또는 "food_spot_search"를 선택하세요.
  - "itinerary_planner" / "food_spot_search"는 장소 선별 기준이
    '평점 4.0 이상 + 높은 평점 우선'임을 전제로 계획하세요.


--------------------------------------------------

[교통 관련 규칙]

두 장소 사이 이동 질문이면

→ transportation_search

예:

서울역 → 광화문  
도쿄역 → 시부야

args 생성 규칙

{
  "origin": "출발지",
  "destination": "도착지",
  "mode": "ALL"
}



--------------------------------------------------

[여러 장소 이동 규칙]

사용자가 **3개 이상의 장소를 순서대로 방문하는 경우**

→ 반드시 transportation_batch 사용


예:

"가천대역에서 고속터미널역 갔다가 서울대학교 갔다가 천안역"

→ stops

[
"가천대역",
"고속터미널역",
"서울대학교",
"천안역"
]


args 예

{
  "stops": [
    "가천대역",
    "고속터미널역",
    "서울대학교",
    "천안역"
  ],
  "mode": "ALL"
}



다음 표현이 나오면 batch 가능성이 매우 높습니다

- 갔다가
- 들렀다가
- 경유
- 거쳐
- 찍고
- → (화살표)

--------------------------------------------------

[여행경보 관련 규칙]

- 사용자가 특정 국가/지역의 여행경보를 물어보면 travel_warning_search를 선택하세요.
- 국가명/지역명이 명확하면 args에 넣으세요.

travel_warning_search args 예:
{
  "country": "일본"
}

- 사용자가 "이 나라 안전해?", "위험한 지역 있어?", "출국권고 지역 있어?"처럼 물으면
  최신 여행경보 정보를 조회하는 도구로 판단하세요.


--------------------------------------------------

[출력 형식]

반드시 아래 JSON 형식만 출력하세요.


{
  "intent": "<위 도구 목록 중 하나>",
  "tools": ["<도구 이름1>", "<필요하면 추가 도구>"],
  "subtasks": [
    "이번 턴에서 해야 할 세부 작업 1",
    "세부 작업 2 ..."
  ],
  "trip_stage": "<ideation | planning | booking | post_trip 중 하나>",
  "args": {}
}



--------------------------------------------------

[규칙]

- tools 배열의 첫 번째 요소가 메인 도구입니다.
- 보통 1개만 넣고, 정말 필요할 때만 2개까지 사용할 수 있습니다.
- trip_stage는 사용자의 진행 상황을 추론해서 적절히 선택하세요.
- 여행과 거의 무관하면 intent = "out_of_scope", tools = ["out_of_scope"], trip_stage = "ideation"으로 둡니다.
- args는 필요한 경우에만 채웁니다.
- transportation_search / transportation_batch는 반드시 args를 채워야 합니다.
- travel_warning_search는 가능하면 args.country를 채우세요.
- JSON 이외의 텍스트는 출력하지 마세요.
- 코드블록 마크다운(```)도 출력하지 마세요.
"""


def _call_planner_llm(planner_context: str, user_message: str) -> str:
    """
    LLM을 한 번 호출해서 JSON 문자열(또는 JSON처럼 생긴 텍스트)을 받아온다.
    """
    user_prompt = f"""
[CONTEXT]
{planner_context}

[USER_MESSAGE]
{user_message}

위 정보를 바탕으로 이번 턴에 사용할 intent/tools/subtasks/trip_stage를
앞서 설명한 JSON 형식으로만 출력해 주세요.
"""
    resp = client.chat.completions.create(
        model="gpt-4.1-mini",
        messages=[
            {"role": "system", "content": PLANNER_SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.2,
    )
    return (resp.choices[0].message.content or "").strip()


def plan_tasks(planner_context: str, user_message: str) -> Dict[str, Any]:
    """
    메인 플래너 함수.
    """
    # 1) 아주 간단한 rule 기반으로 '완전 여행 밖'인 경우 빠르게 out_of_scope로 처리
    lower = user_message.lower()
    if any(
        kw in lower
        for kw in [
            "헬스", "운동", "다이어트", "주식", "코인", "투자",
            "이직", "퇴사", "연애", "썸", "코딩", "프로그래밍",
        ]
    ) and "여행" not in lower and "trip" not in lower:
        return {
            "intent": "out_of_scope",
            "tools": ["out_of_scope"],
            "subtasks": ["여행 범위를 벗어난 질문임을 알리고, 여행 주제로 다시 유도한다."],
            "trip_stage": "ideation",
            "args": {},
        }

    # 2) LLM에게 맡겨서 plan JSON 생성
    raw = _call_planner_llm(planner_context, user_message)

    # 3) JSON 파싱 시도
    try:
        plan = json.loads(raw)
    except Exception:
        # 혹시 텍스트 안에 { ... }만 골라낼 수 있으면 골라서 다시 시도
        try:
            start = raw.index("{")
            end = raw.rindex("}") + 1
            plan = json.loads(raw[start:end])
        except Exception:
            # 완전히 실패하면 안전한 fallback
            plan = {
                "intent": "general_chat",
                "tools": ["general_chat"],
                "subtasks": ["사용자의 여행 고민을 듣고 다음에 무엇을 정하면 좋을지 도와준다."],
                "trip_stage": "ideation",
                "args": {},
            }

    # 4) 보정: 필드 누락/형식 이상 시 기본값 채우기
    intent = plan.get("intent") or "general_chat"
    tools = plan.get("tools") or [intent]
    if isinstance(tools, str):
        tools = [tools]
    subtasks = plan.get("subtasks") or ["사용자의 여행 고민에 맞춰 다음 단계를 함께 정한다."]
    trip_stage = plan.get("trip_stage") or "ideation"

    args = plan.get("args") or {}
    if not isinstance(args, dict):
        args = {}

    cleaned = {
        "intent": intent,
        "tools": tools,
        "subtasks": subtasks,
        "trip_stage": trip_stage,
        "args": args,
    }
    return cleaned
