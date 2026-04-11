# prompts.py
import json
from datetime import datetime
from typing import Optional

# ==============================================================================
# [공통 제어 규칙 1] 대답 생성용 (특수문자 제거 + 날짜 동기화)
# ==============================================================================
def get_strict_output_rule() -> str:
    now = datetime.now()
    today_date = now.strftime("%Y-%m-%d")
    current_year = now.year
    return f"""
    [출력 규칙 및 실시간 날짜 동기화 - 엄격 적용]
    1. 인사말, 부연 설명, 맺음말 등 불필요한 문장 절대 금지.
    2. 마크다운 기호(별표, 샵, 하이픈 등), 이모지, 화살표 등 특수문자 일절 사용 금지. (볼드체 금지, 모든 대답에서 별표 기호 절대 사용 금지)
    3. 오직 질문에 대한 핵심 정보만 평문과 숫자로 가장 짧고 간결하게 대답할 것.
    4. [중요] 오늘 날짜는 {today_date}입니다. 사용자가 연도를 생략하거나 과거로 추론될 경우, 무조건 올해({current_year}년) 및 미래 날짜를 기준으로 안내하세요.
    """

# ==============================================================================
# [공통 제어 규칙 2] 시스템 내부 JSON 파라미터 및 플래너용 (날짜 강제)
# ==============================================================================
def get_dynamic_date_rule() -> str:
    now = datetime.now()
    today_date = now.strftime("%Y-%m-%d")
    current_year = now.year
    return f"""
    [절대 규칙: 실시간 날짜 동기화]
    - 오늘 날짜는 {today_date}입니다. 
    - 연도를 명시하지 않았거나 과거 날짜로 계산될 경우, 무조건 올해({current_year}년) 또는 다가오는 미래 날짜로 자동 업데이트하여 적용하세요! (과거 날짜 사용 엄격 금지)
    """

# (정적 프롬프트를 위한 초기 날짜 세팅)
_NOW = datetime.now()
_TODAY = _NOW.strftime("%Y-%m-%d")
_YEAR = _NOW.year

# ==============================================================================
# [1] Tools 프롬프트 (tools.py 관련)
# ==============================================================================

# 1-1. 여행지 아이데이션
IDEATION_SYSTEM = "당신은 여행 큐레이터입니다."

def build_ideation_user_prompt(context: str, user_message: str) -> str:
    return f"""
    [대화 맥락] {context}
    [사용자 요청] {user_message}
    
    사용자의 취향, 예산, 계절감을 고려해 여행지 3~5곳을 추천하고 이유를 설명하세요.
    {get_strict_output_rule()}
    """

# 1-2. 일정 플래너
ITINERARY_PARAM_PROMPT = """
사용자의 요청에서 'destination'과 'is_korea'(한국 여부, boolean)를 추출하세요.
JSON 형식으로만 출력: {"destination": "Jeju", "is_korea": true}
"""

ITINERARY_SYSTEM = "당신은 여행 플래너입니다. 동선과 효율성을 고려해 일정을 계획합니다."

def build_itinerary_user_prompt(user_message: str, places_info: str, weather_info_text: str) -> str:
    return f"""
    [사용자 요청] {user_message}
    [검색된 장소 데이터] {places_info}
    {weather_info_text}
    
    [지침 - 엄격 준수]
    1. [최상단 날씨 및 옷차림 안내] 답변의 가장 첫 줄에 날짜별로 오전, 오후 날씨(기온, 맑음/비 등 상태, 강수확률)를 정확하게 나누어 평문으로 작성하고, 사용자가 옷차림을 정하기 쉽도록 적절한 팁을 짧게 덧붙이세요.
    2. [일정 구성] 검색된 장소 데이터를 우선 활용하되, 날씨가 좋으면 야외, 비가 오면 실내 위주로 동선을 짜세요.
    3. [이동 수단] 대중교통: 노선명, 환승지, 도보 포함 소요 시간 명시. 택시: 소요 시간 및 현지 통화 기준 예상 요금 필수 포함.
    4. [하단 축제 추천] 모든 일정 작성이 끝난 후, 맨 아래에 "이번 여행 중 즐길 수 있는 축제/행사" 섹션을 만드세요. 검색 데이터에 축제가 있다면 명칭, 장소, 일시를 요약하고, 데이터가 없다면 해당 지역의 대표적인 상시 행사나 시즌 이벤트를 간결하게 제안하세요.

    (출력 형식 예시)
    날짜: 5월 15일
    날씨: 오전 15도(맑음, 강수 0%), 오후 22도(구름조금, 강수 10%)
    옷차림 팁: 일교차가 크니 얇은 겉옷을 챙기세요.
    
    10:00 유니버셜 스튜디오 재팬
    위치: 오사카시 고노하나구
    이동: [대중교통] 난바역에서 한신 난바선 탑승 후 니시쿠조역에서 JR 유메사키선 환승 (약 25분) / [택시] 약 15분 (예상 요금: 약 3,500엔)
    
    이번 여행 중 즐길 수 있는 축제/행사
    오사카 벚꽃 축제 (오사카성 공원): 3월 말 ~ 4월 초 / 야간 라이트업 진행
       
    {get_strict_output_rule()}
    """

# 1-3. 항공권 검색 파라미터
def build_flight_param_prompt() -> str:
    return f"""
    항공권 파라미터를 추출하세요. 
    {get_dynamic_date_rule()}
    
    1. origin, destination은 반드시 IATA 공항 코드 3자리 대문자로 출력하세요. (예: ICN, OSA, NRT)
       - 사용자가 출발지를 말하지 않았으면 무조건 "ICN"을 기본값으로 출력하세요. ("미정" 등 한글 절대 금지)
    2. departureDate, returnDate는 반드시 하이픈(-)이 포함된 "YYYY-MM-DD" 형식이어야 합니다. (공백 사용 금지)
    
    JSON 형식: {{"origin": "ICN", "destination": "OSA", "departureDate": "{_YEAR}-05-15", "return_date": "{_YEAR}-05-18" or null}}
    """

# 1-4. 숙소 검색
STAY_PARAM_PROMPT = f"""
추출: destination, check_in(YYYY-MM-DD), check_out, guests(int).
오늘 날짜는 {_TODAY}입니다. 과거 날짜로 추론하지 말고, 무조건 올해({_YEAR}년) 이후의 미래 날짜로 설정하세요.
JSON: {{"destination": "Seoul", "check_in": "{_YEAR}-05-01", "check_out": "{_YEAR}-05-05", "guests": 2}}
"""

STAY_SYSTEM = "호텔 컨시어지로서 최적의 숙소를 추천합니다."

def build_stay_user_prompt(user_message: str, raw_text: str) -> str:
    return f"""사용자 요청: {user_message}
[통합 숙소 데이터]
{raw_text}

[필수 지침]
위 데이터 중 가장 추천할 만한 상위 3곳의 숙소를 골라 이름, 가격, 평점을 안내해 주세요. (1개만 안내하지 말고 반드시 3곳을 선정할 것)
{get_strict_output_rule()}
"""

# 1-5. 맛집/명소 검색
FOOD_PARAM_PROMPT = """
추출 'query' (검색어)와 'place_type' (restaurant 또는 tourist_attraction).
JSON: {"query": "상하이 맛집", "place_type": "restaurant"}
"""

FOOD_SYSTEM = "미식 및 명소 가이드입니다."

def build_food_user_prompt(user_message: str, data_text: str) -> str:
    return f"""요청: {user_message}
데이터:
{data_text}
{get_strict_output_rule()}
"""

# 1-6. 축제/이벤트 검색
def build_event_param_prompt(context: str) -> str:
    return f"""
    사용자의 요청에서 축제, 행사, 전시회 검색을 위한 파라미터를 추출하세요. 
    {get_dynamic_date_rule()}
    JSON 형식으로만 출력: {{"country": "한국", "region": "서울", "query": "서울 전시회", "start_date": "{_TODAY}"}}
    """

EVENT_SYSTEM = "전문 여행 가이드입니다."

def build_event_user_prompt(user_message: str, data_text: str) -> str:
    return f"""사용자 요청: {user_message}
[검색된 실시간 데이터 리스트]
{data_text}
{get_strict_output_rule()}
"""

# 1-7. 현지 가이드
LOCAL_GUIDE_PARAM_PROMPT = """
사용자의 요청이 'A에서 B로 가는 방법'처럼 특정 경로의 교통편을 묻는 것이라면 출발지와 도착지를 추출하세요.
JSON: {"origin": "신주쿠역", "destination": "시부야 스카이"}
"""

LOCAL_GUIDE_SYSTEM = "현지 교통 가이드입니다."

def build_local_guide_user_prompt(context: str, user_message: str, transit_data: str) -> str:
    return f"""
    [대화 맥락] {context}
    [사용자 질문] {user_message}
    {transit_data}
    {get_strict_output_rule()}
    """

# 1-8. 예약 실행
def build_booking_param_prompt() -> str:
    return f"""
    예약 파라미터를 추출하세요. 
    {get_dynamic_date_rule()}
    
    - booking_type: "hotel" 또는 "flight" (항공권 관련 단어가 있으면 무조건 "flight")
    - destination: 목적지 IATA 공항 코드 3자리 대문자 (예: OSA, NRT). 
    - destination_kr: 목적지 한국어명 (예: 오사카)
    - check_in / departure_date: (YYYY-MM-DD 형식, 하이픈 필수)
    - check_out / return_date: (YYYY-MM-DD 형식, 하이픈 필수)
    - guests: 인원 수 (int, 기본 2)
    - origin: 출발 공항 IATA 코드 (언급 없으면 무조건 "ICN", "미정" 절대 금지)
    - item_index: 사용자가 대화 중 숙소 이름이나 순서(첫 번째 등)를 지정해 예약을 확정하려고 한 경우, 해당 항목의 0부터 시작하는 숫자 인덱스(0, 1, 2). 지정하지 않았다면 null.

    JSON만 출력:
    {{"booking_type": "hotel", "destination": "OSA", "destination_kr": "오사카", "check_in": "{_YEAR}-05-15", "check_out": "{_YEAR}-05-18", "departure_date": null, "return_date": null, "guests": 2, "origin": "ICN", "item_index": 0}}
    """

# 1-9. 기타
BUDGET_SYSTEM = "예산 전문가입니다."
DEFAULT_AGENT_SYSTEM = "여행 에이전트입니다. 마크다운 기호나 특수문자 없이 간결하게 대답하세요."


# ==============================================================================
# [2] Planner 프롬프트 (planner.py 관련)
# ==============================================================================
PLANNER_SYSTEM_PROMPT = """
당신은 여행 전용 플래너(Planner)입니다. 사용자의 질문에 여러 요구사항이 포함된 경우, 'tools' 배열에 필요한 모든 도구를 포함하세요.

[판단 규칙]
1. 사용자가 날씨를 물으면 반드시 "local_guide"를 포함하세요.
2. 축제, 행사, 전시회를 물으면 반드시 "event_search"를 포함하세요.
3. 일정과 함께 날씨/행사를 물으면 ["itinerary_planner", "local_guide", "event_search"] 처럼 모두 포함해야 합니다.

[도구 목록]
- "trip_ideation" : 목적지 제안
- "itinerary_planner" : 일정 계획 (구글맵 4.0 이상, 한국은 네이버 보완)
- "flight_search" : 항공권 검색
- "stay_search" : 숙소 지역 추천 및 검색 리스트 보기 (3곳 추천)
- "booking_action" : 실제 예약 진행/확정 호출 ([매우 중요] 사용자가 특정 호텔이나 항공권을 고른 뒤 예약 확정을 요청할 때는 무조건 이 도구만 사용)
- "food_spot_search" : 맛집/카페 검색 (구글맵 4.0 이상, 한국은 네이버 보완)
- "local_guide" : 현지 정보 안내 (교통, 날씨 등)
- "budget_planner" : 예산 배분 전략
- "transportation_search" : 두 장소 사이 이동 수단 검색 (args: origin, destination, mode)
- "transportation_batch" : 여러 장소 순서대로 이동 (args: stops 배열, mode)
- "travel_warning_search" : 여행경보, 출국권고 등 (args: country)
- "event_search" : 축제, 이벤트 검색
- "general_chat" : 여행 관련 고민/잡담
- "out_of_scope" : 여행과 무관한 요청 거절

[trip_stage]
- "ideation", "planning", "booking", "post_trip"

[출력 형식]
반드시 아래 JSON 형식만 출력하세요. (코드블록 마크다운 금지)
{
  "intent": "<위 도구 목록 중 하나>",
  "tools": ["<도구 이름1>"],
  "subtasks": ["세부 작업"],
  "trip_stage": "<진행 단계>",
  "args": {}
}
"""

def build_planner_user_prompt(planner_context: str, user_message: str) -> str:
    return f"""
[CONTEXT]
{planner_context}

[USER_MESSAGE]
{user_message}

{get_dynamic_date_rule()}
위 정보를 바탕으로 이번 턴에 사용할 intent/tools/subtasks/trip_stage를 앞서 설명한 JSON 형식으로만 출력해 주세요.
"""


# ==============================================================================
# [3] Graph Nodes 메모리 관리 프롬프트 (graph_nodes.py 관련)
# ==============================================================================
def build_context_summary_prompt(current_context: str, convo_text: str) -> str:
    return f"""
    너는 여행 대화의 메모리 관리자다.
    아래 '이전 요약'과 '최근 대화'를 읽고, 반드시 지정한 형식으로만 업데이트된 요약을 작성하라. 절대 별표 기호를 쓰지 마라.
    {get_dynamic_date_rule()}

    [중요] 이전 요약에 '[필수 적용 - 사용자 여행 성향 설문결과]' 섹션이 있다면, 해당 내용을 절대 삭제하지 말고 요약 맨 앞에 그대로 유지하라.

    [이전 요약]
    {current_context}

    [최근 대화]
    {convo_text}

    [출력 형식 - 반드시 그대로]
    목적지: <도시/국가 또는 미정>
    기간: <YYYY-MM-DD ~ YYYY-MM-DD 또는 미정>
    박/일: <n박 m일 또는 미정>
    인원: <숫자 또는 미정>
    출발지: <도시 또는 미정>
    예산: <상한/범위/통화 또는 미정>
    항공 조건: <직항/경유/항공사 선호/제외/좌석 등급 등, 없으면 '없음'>
    숙소 조건: <동네/숙소타입/가격대/후기기준 등, 없으면 '없음'>
    일정/관심사: <핵심 일정/관심 키워드, 없으면 '없음'>
    확정된 결정: <확정된 내용 기재, 없으면 '없음'>
    미해결 질문: <사용자에게 추가로 물어봐야 할 것, 없으면 '없음'>
    """


# ==============================================================================
# [4] 여행 목표 추출 프롬프트 (goal_service.py 관련)
# ==============================================================================
GOAL_EXTRACTION_SYSTEM = """
당신은 '여행 장기 목표 추출기'입니다.
진행 중인 주 여행 1개를 JSON으로만 정리하세요.
출력 JSON 필드: destination, nights, days, month, budget_krw, style_tags, status
"""

def build_goal_extraction_user_prompt(context: str, user_message: str, previous_goal: Optional[dict]) -> str:
    prev_goal_str = json.dumps(previous_goal, ensure_ascii=False) if previous_goal else "null"
    return f"""
[CONTEXT] {context}
[USER MESSAGE] {user_message}

현재 준비 중인 '대표 여행 1개'를 JSON으로 정리하세요. JSON만 출력하세요. 불명확한 정보는 null로 두세요.
{get_dynamic_date_rule()}
이전 여행 목표: {prev_goal_str}
"""


# ==============================================================================
# [5] 데이터 요약 프롬프트 (gemini_service.py 관련)
# ==============================================================================
FLIGHT_SUMMARY_SYSTEM = "당신은 항공권 컨설턴트입니다."

def build_flight_summary_user_prompt(user_query: str, flight_raw_data: str) -> str:
    return f"""
    [사용자 질문] {user_query}
    [항공권 데이터] {flight_raw_data}
    
    가장 추천할 만한 옵션 3가지를 정리하세요. URL은 그대로 출력하세요.
    {get_strict_output_rule()}
    """