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
# [공통 제어 규칙 3] 설문 기반 페르소나 및 맞춤형 추천 규칙
# ==============================================================================
def get_survey_persona_rule(survey: dict) -> str:
    """숙소, 기본 응답 등 범용적으로 사용되는 페르소나 지침"""
    if not survey:
        return ""
    
    rules = []
    
    atmosphere = survey.get('atmosphere', '')
    if '도심' in atmosphere:
        rules.append("- 🏙️ [분위기]: 번화가, 대형 쇼핑몰, 핫플레이스, 야경 명소 위주로 추천하세요.")
    elif '자연' in atmosphere:
        rules.append("- 🌿 [분위기]: 국립공원, 바다, 숲, 한적하고 조용한 힐링 스팟 위주로 추천하세요.")
    
    budget = survey.get('budget', '')
    if '가성비' in budget:
        rules.append("- 💰 [숙소/맛집]: 3성급 이하 가성비 숙소, 로컬 길거리 음식이나 가성비 식당을 우선 추천하세요.")
    elif '프리미엄' in budget:
        rules.append("- ✨ [숙소/맛집]: 4~5성급 고급 호텔/리조트, 파인다이닝, 분위기 좋은 럭셔리 식당을 우선 추천하세요.")
        
    if not rules:
        return ""
        
    persona_text = "\n".join(rules)
    return f"""
    [🔥 사용자 맞춤형 추천 절대 지침 🔥]
    사용자의 사전 설문 결과에 따라 아래 지침을 1순위로 반영하여 답변하세요. 이 지침에 어긋나는 추천은 피해야 합니다.
    {persona_text}
    """

def get_itinerary_survey_rule(survey: dict) -> str:
    """일정(Itinerary) 작성을 위한 전용 페르소나 지침"""
    if not survey:
        return ""
    
    rules = ["[🔥 일정 추천 절대 지침 🔥] 사용자의 성향에 맞춰 아래 규칙을 1순위로 적용하여 일정을 작성하세요."]
    
    atmosphere = survey.get('atmosphere', '')
    if '도심' in atmosphere:
        rules.append("- [동선 컨셉]: 랜드마크, 번화가, 핫플레이스, 야경 명소를 중심으로 동선을 짜세요.")
    elif '자연' in atmosphere:
        rules.append("- [동선 컨셉]: 공원, 바다, 산책로 등 자연경관이 뛰어나고 한적한 힐링 스팟을 포함하세요.")
    
    priority = survey.get('priority', '')
    if '관람' in priority:
        rules.append("- [주요 스팟]: 유명 관광지, 박물관, 액티비티를 하루 2~3개 이상 포함하세요.")
    elif '식도락' in priority:
        rules.append("- [주요 스팟]: 식사와 디저트가 메인입니다. 명소보다 '유명 맛집/카페'를 중심으로 동선을 짜고, 식사 시간을 넉넉히 배정하세요.")
    elif '휴식' in priority:
        rules.append("- [주요 스팟]: 일정을 무리하게 잡지 마세요. 뷰가 좋은 카페나 숙소 근처 산책 등 정적인 활동을 배치하세요.")

    schedule = survey.get('schedule', '')
    if '계획' in schedule:
        rules.append("- [일정표 형식]: 오전 09:00부터 저녁 21:00까지 시간대별로 촘촘하게 분 단위/시간 단위 일정을 작성하세요. 장소 간 이동 시간과 수단도 명시하세요.")
    elif '즉흥' in schedule:
        rules.append("- [일정표 형식]: 시간표를 빡빡하게 짜지 마세요! '오전 추천 스팟 1개', '오후 추천 스팟 1개' 식으로 큼직하게 제안하고, 발길 닿는 대로 갈 수 있는 주변 옵션(플랜B)을 가볍게 덧붙이세요.")
    else:
        rules.append("- [일정표 형식]: 하루에 반드시 가야 할 핵심 명소 1~2개만 고정하고, 나머지 시간은 유동적으로 쓸 수 있게 여유롭게 배치하세요.")

    return "\n".join(rules)

def get_flight_survey_rule(survey: dict) -> str:
    """항공권(Flight) 검색을 위한 전용 페르소나 지침"""
    if not survey:
        return ""
    
    rules = ["[🔥 항공권 추천 절대 지침 🔥] 사용자의 성향에 맞춰 아래 기준을 바탕으로 상위 3개의 항공권을 골라주세요."]
    
    budget = survey.get('budget', '')
    if '가성비' in budget:
        rules.append("- [우선순위]: '최저가'가 최우선입니다. 새벽/밤 비행기나 저가항공(LCC)이더라도 가격이 저렴한 옵션을 1순위로 추천하세요.")
    elif '프리미엄' in budget:
        rules.append("- [우선순위]: '편안함'이 최우선입니다. 대형항공사(FSC) 직항을 우선 추천하고, 너무 이른 새벽이나 심야 비행기는 제외하세요.")
    
    schedule = survey.get('schedule', '')
    if '계획' in schedule:
        rules.append("- [시간대]: 현지 체류 시간을 극대화할 수 있는 '아침 출국 - 저녁 귀국' 꽉 찬 일정의 항공권을 추천하세요.")
    elif '즉흥' in schedule or '휴식' in survey.get('priority', ''):
        rules.append("- [시간대]: 피로도를 낮추기 위해 '오후 출발'이나 '낮 시간대 도착' 등 수면 패턴을 해치지 않는 여유로운 시간대의 항공권을 포함해 보세요.")

    return "\n".join(rules)


# ==============================================================================
# [1] Tools 프롬프트 (tools.py 관련)
# ==============================================================================

# 1-1. 여행지 아이데이션
IDEATION_SYSTEM = "당신은 여행 큐레이터입니다."

def build_ideation_user_prompt(context: str, user_message: str, survey: dict = None) -> str:
    persona_rule = get_survey_persona_rule(survey)
    return f"""
    [대화 맥락] {context}
    [사용자 요청] {user_message}
    
    {persona_rule}
    
    사용자의 취향, 예산, 계절감을 고려해 여행지 3~5곳을 추천하고 이유를 설명하세요.
    {get_strict_output_rule()}
    """

# 1-2. 일정 플래너
ITINERARY_PARAM_PROMPT = """
사용자의 요청에서 'destination'과 'is_korea'(한국 여부, boolean)를 추출하세요.
JSON 형식으로만 출력: {"destination": "Jeju", "is_korea": true}
"""

ITINERARY_SYSTEM = "당신은 여행 플래너입니다. 동선과 효율성을 고려해 일정을 계획합니다."

def build_itinerary_user_prompt(user_message: str, places_info: str, weather_info_text: str, survey: dict = None) -> str:
    survey_rule = get_itinerary_survey_rule(survey)
    return f"""
    [사용자 요청] {user_message}
    [검색된 장소 데이터] {places_info}
    {weather_info_text}
    
    {survey_rule}
    
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

def build_stay_user_prompt(user_message: str, raw_text: str, survey: dict = None) -> str:
    persona_rule = get_survey_persona_rule(survey)
    return f"""사용자 요청: {user_message}
[통합 숙소 데이터]
{raw_text}

{persona_rule}

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

def build_food_user_prompt(user_message: str, data_text: str, survey: dict = None) -> str:
    persona_rule = get_survey_persona_rule(survey)
    return f"""요청: {user_message}
데이터:
{data_text}

{persona_rule}

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

# 1-8. 예약 실행 (★ 항공권/숙소 인덱스 추출 집중 강화 ★)
def build_booking_param_prompt() -> str:
    return f"""
    예약 시스템 연결을 위한 파라미터를 추출하세요. 
    {get_dynamic_date_rule()}
    
    [추출 규칙]
    1. booking_type: "hotel" 또는 "flight" (항공권, 비행기, 항공사 등이 언급되면 무조건 "flight")
    2. item_index: 사용자가 대화 중 숙소 이름이나 순서를 지정해 예약을 확정하려고 한 경우, 해당 항목의 순서(0부터 시작하는 숫자).
       - 예: "첫 번째", "맨 위", "제일 싼거" -> 0
       - 예: "두 번째", "중간 거" -> 1
       - 예: 항공사명(예: "티웨이", "대한항공")이나 숙소명을 직접 지칭했다면, 리스트에서 해당 이름이 위치할 법한 순서 번호를 할당하세요. 
       - 불명확하다면 기본값 0을 설정하세요. 절대 null로 두지 마세요.
    3. destination: 목적지 IATA 공항 코드 3자리 대문자 (예: OSA, NRT). 
    4. destination_kr: 목적지 한국어명 (예: 오사카)
    5. check_in / departure_date: (YYYY-MM-DD 형식, 하이픈 필수)
    6. check_out / return_date: (YYYY-MM-DD 형식, 하이픈 필수)
    7. guests: 인원 수 (int, 기본 2)
    8. origin: 출발 공항 IATA 코드 (언급 없으면 무조건 "ICN", "미정" 절대 금지)

    JSON만 출력:
    {{"booking_type": "flight", "destination": "OSA", "destination_kr": "오사카", "check_in": null, "check_out": null, "departure_date": "{_YEAR}-05-15", "return_date": "{_YEAR}-05-18", "guests": 2, "origin": "ICN", "item_index": 0}}
    """

# 1-9. 기타
BUDGET_SYSTEM = "예산 전문가입니다."

DEFAULT_AGENT_SYSTEM = """당신은 친절한 여행 에이전트입니다.
사용자의 질문이 명확한 여행 관련 요청이 아니라면(예: 의미 없는 단어, 동문서답), 이전 턴에서 예산이나 인원을 물어봤더라도 억지로 다시 캐묻거나 값을 지어내지 마세요.
"어떤 여행을 계획 중이신가요? 편하게 말씀해 주세요!"라고 대화를 리셋하며 친절하게 물어보세요. 마크다운 기호나 특수문자 없이 간결하게 평문으로 대답하세요."""

OUT_OF_SCOPE_SYSTEM = """당신은 친절하고 다정한 여행 전문 에이전트입니다.
사용자가 여행과 무관한 단어(예: 봉봉, ㅋㅋ, 안녕 등), 일상 대화, 농담, 혹은 다른 분야의 주제를 꺼낼 경우 다음과 같이 대답해야 합니다.

[답변 지침]
1. [핵심] 이전 턴에서 당신이 인원수나 예산, 여행지 등을 물어보았더라도, 사용자가 동문서답을 한다면 절대 이전 질문을 다시 반복해서 캐묻지 마세요.
2. 임의로 인원, 예산, 여행지 등 없는 정보를 지어내어 대답하지 마세요.
3. "저는 여행 전문 에이전트라서 여행에 대한 이야기만 나눌 수 있어요 :) 여행지 추천이나 숙소, 항공권 등 궁금한 점을 편하게 남겨주세요!" 라는 뉘앙스로 대화의 흐름을 리셋하고 부드럽게 대답하세요.
4. 마크다운 기호나 특수문자는 절대 사용하지 말고 평문으로 깔끔하게 작성하세요.
"""

# ==============================================================================
# [2] Planner 프롬프트 (planner.py 관련) ★ 예약 선택 시 무조건 booking_action으로 가도록 규칙 강화 ★
# ==============================================================================
PLANNER_SYSTEM_PROMPT = """
당신은 여행 전용 플래너(Planner)입니다. 사용자의 질문에 여러 요구사항이 포함된 경우, 'tools' 배열에 필요한 모든 도구를 포함하세요.

[판단 규칙]
1. [매우 중요] 사용자가 추천된 항공권이나 숙소 리스트 중 하나를 선택하여 예약을 확정하려는 의도(예: "첫 번째 걸로 예약해줘", "티웨이로 할게", "이 숙소 결제할래")가 보이면 **무조건 "booking_action" 도구만 사용**하세요.
2. 단순히 숙소 리스트를 추천해 달라고 하거나, 항공권 가격을 물어보면 "flight_search"나 "stay_search"를 유지하세요.
3. 사용자가 날씨를 물으면 반드시 "local_guide"를 포함하세요.
4. 축제, 행사, 전시회를 물으면 반드시 "event_search"를 포함하세요.
5. 일정과 함께 날씨/행사를 물으면 ["itinerary_planner", "local_guide", "event_search"] 처럼 모두 포함해야 합니다.

[도구 목록]
- "booking_action" : 실제 예약 진행/확정 호출 (args: booking_type, item_index 필수 포함)
- "trip_ideation" : 목적지 제안
- "itinerary_planner" : 일정 계획 (구글맵 4.0 이상, 한국은 네이버 보완)
- "flight_search" : 항공권 검색
- "stay_search" : 숙소 지역 추천 및 검색 리스트 보기 (3곳 추천)
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

def build_flight_summary_user_prompt(user_query: str, flight_raw_data: str, survey: dict = None) -> str:
    survey_rule = get_flight_survey_rule(survey)
    return f"""
    [사용자 질문] {user_query}
    [항공권 데이터] {flight_raw_data}
    
    {survey_rule}
    
    가장 추천할 만한 옵션 3가지를 정리하세요. URL은 그대로 출력하세요.
    {get_strict_output_rule()}
    """