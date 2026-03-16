# tools.py
import os
import re
import json
from datetime import datetime
import amadeus
from typing import Dict, Any, List, Optional

from dotenv import load_dotenv
from openai import OpenAI

# [서비스 모듈 임포트]
from naver_service import search_places_naver
from google_maps_service import search_places_google, get_directions_info
from crawl_accommodation_tripadvisor import search_hotels_with_retry as search_tripadvisor
from crawl_accommodation_booking_com import search_hotels_api as search_booking
from crawl_accommodation_amadeus import search_hotels_api as search_amadeus
from flight_service import search_flight_offers
from transportation_service import render_transport_options, render_transport_batch
from event_service import search_events_serpapi, search_korea_festivals_tourapi

# [Gemini 서비스 임포트]
from gemini_service import call_gemini, summarize_flight_data

load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# 마지막 항공권 검색 파라미터(대화 내 후속 질문에서 재사용)
_LAST_FLIGHT_PARAMS: Dict[str, Any] = {}

# -------------------------------------------------------------------
# [Helper] OpenAI를 이용한 '정확한' 파라미터 추출
# -------------------------------------------------------------------
def extract_params_with_openai(system_prompt: str, user_message: str, context: str) -> Dict[str, Any]:
    """OpenAI(GPT-4)를 사용하여 JSON 파라미터만 정확히 추출"""
    try:
        resp = client.chat.completions.create(
            model="gpt-4-turbo", 
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"[Context]\n{context}\n\n[Message]\n{user_message}"},
            ],
            response_format={"type": "json_object"},
            temperature=0,
        )
        return json.loads(resp.choices[0].message.content or "{}")
    except Exception as e:
        print(f"⚠️ Parameter Extraction Error: {e}")
        return {}


# -------------------------------------------------------------------
# 1. 여행지 아이데이션 (Gemini 창작)
# -------------------------------------------------------------------
def run_trip_ideation_tool(user_message: str, context: str) -> str:
    system_prompt = "당신은 창의적인 여행 큐레이터입니다."
    user_prompt = f"""
    [대화 맥락]
    {context}
    
    [사용자 요청]
    {user_message}
    
    사용자의 취향, 예산, 계절감을 고려해 여행지 3~5곳을 추천하고, 그 이유를 매력적으로 설명해 주세요.
    """
    return call_gemini(system_prompt, user_prompt, temperature=0.7)


# -------------------------------------------------------------------
# 2. 일정 플래너 (OpenAI 추출 -> 지도 API -> Gemini 작성)
# -------------------------------------------------------------------
def run_itinerary_planner_tool(user_message: str, context: str) -> str:
    print("RUNNING: Itinerary Planner")
    
    param_prompt = """
    사용자의 요청에서 'destination'과 'is_korea'(한국 여부, boolean)를 추출하세요.
    JSON 형식으로만 출력: {"destination": "Jeju", "is_korea": true}
    """
    params = extract_params_with_openai(param_prompt, user_message, context)
    destination = params.get("destination", "여행지")
    is_korea = params.get("is_korea", False)

    places_info = ""
    print(f"🔎 '{destination}' 장소 검색 중... (한국여부: {is_korea})")
    
    g_spots = search_places_google(f"{destination} tourist attraction", "tourist_attraction", min_rating=4.0)
    g_food = search_places_google(f"{destination} restaurant", "restaurant", min_rating=4.0)
    
    if g_spots or g_food:
        places_info += f"\n[Google Maps Data for {destination}]\n"
        for p in g_spots[:5]: places_info += f"- (명소) {p['name']} (★{p['rating']}, 리뷰 {p['user_ratings_total']})\n"
        for p in g_food[:5]: places_info += f"- (맛집) {p['name']} (★{p['rating']}, 리뷰 {p['user_ratings_total']})\n"

    if is_korea:
        n_spots = search_places_naver(f"{destination} 가볼만한곳")
        n_food = search_places_naver(f"{destination} 맛집")
        if n_spots or n_food:
            places_info += f"\n[Naver Maps Data (Backup)]\n"
            for p in n_spots[:5]: places_info += f"- (명소) {p['title']}\n"
            for p in n_food[:5]: places_info += f"- (맛집) {p['title']}\n"

    system_prompt = "당신은 전문 여행 플래너이자 완벽한 길잡이입니다. 장소의 매력뿐만 아니라 이동 동선까지 치밀하게 계산합니다."
    user_prompt = f"""
    [사용자 요청] {user_message}
    [검색된 장소 데이터] {places_info}
    
    위 데이터를 활용하여 실현 가능한 일정을 짜주세요. 
    
    🔥 [필수 포함 사항 - 교통 가이드] 🔥
    단순히 장소만 나열하지 말고, **장소와 장소 사이의 이동 수단과 예상 소요 시간**을 반드시 구체적으로 명시해 주세요.
    (예시: "📌 A 명소 관광 -> 🚶 도보 10분 -> 📌 B 식당", "📌 B 식당 -> 🚌 버스 15번 (약 20분 소요) -> 📌 C 카페")
    동선이 꼬이지 않도록 구글 맵스 데이터를 기반으로 가장 효율적인 순서를 제안하세요.
    """
    return call_gemini(system_prompt, user_prompt, temperature=0.4)


# -------------------------------------------------------------------
# 3. 항공권 검색 (개선됨: 400 에러 방지 로직 추가)
# -------------------------------------------------------------------
def run_flight_search_tool(user_message: str, context: str) -> str:
    print("RUNNING: Flight Search")
    
    # 현재 연도(2026)를 명시하여 과거 날짜 검색 방지
    current_year = datetime.now().year 
    
    param_prompt = f"""
    항공권 파라미터를 추출하세요. 현재 연도는 {current_year}년입니다.
    1. origin, destination은 반드시 IATA 공항 코드(3자리 대문자, 예: ICN, PVG, NRT)로 변환하세요.
    2. departureDate, returnDate는 반드시 YYYY-MM-DD 형식이어야 합니다.
    3. 사용자가 "3월"이라고만 하면 {current_year}-03-15 정도로 추측하세요.
    JSON 형식: {{"origin": "ICN", "destination": "PVG", "departureDate": "YYYY-MM-DD", "return_date": "YYYY-MM-DD" or null}}
    """
    params = extract_params_with_openai(param_prompt, user_message, context)
    
    origin = params.get("origin", "ICN")
    dest = params.get("destination")
    dep_date = params.get("departureDate")
    ret_date = params.get("return_date")

    if not dest or not dep_date:
        return "출발지, 목적지 또는 날짜 정보가 부족하여 항공권을 검색할 수 없습니다. (예: 3월 상하이 항공권 알려줘)"

    print(f"✈️ API 호출 파라미터: {origin} -> {dest}, 날짜: {dep_date}")

    try:
        # flight_service.py의 검색 함수 호출
        flight_data = search_flight_offers(origin, dest, dep_date, ret_date)
    except Exception as e:
        flight_data = f"항공권 검색 중 API 오류가 발생했습니다: {str(e)}"

    # Gemini를 통해 최종 답변 작성
    return summarize_flight_data(user_message, flight_data)


# -------------------------------------------------------------------
# 4. 숙소 검색
# -------------------------------------------------------------------
def run_stay_search_tool(user_message: str, context: str) -> str:
    print("RUNNING: Stay Search")
    
    param_prompt = """
    추출: destination, check_in(YYYY-MM-DD), check_out, guests(int).
    JSON: {"destination": "Seoul", "check_in": "2026-05-01", "check_out": "2026-05-05", "guests": 2}
    """
    params = extract_params_with_openai(param_prompt, user_message, context)
    print("[DEBUG] extract_search_params 결과:", params)
    
    destination = params.get("destination")
    check_in = params.get("check_in")
    check_out = params.get("check_out")
    guests = params.get("guests", 2)
    
    if not destination:
        return "어느 지역의 숙소를 찾아드릴까요? 도시 이름을 말씀해 주세요."

    ## 다중 API 호출 및 데이터 통합
    all_accommodations = []

    # (A) TripAdvisor
    try:
        ta_results = search_tripadvisor(destination, check_in, check_out)
        if ta_results:
            for item in ta_results: item['source'] = 'TripAdvisor'
            all_accommodations.extend(ta_results)
    except Exception as e: print(f"TripAdvisor Error: {e}")

    # (B) Booking.com
    try:
        bk_results = search_booking(destination, check_in, check_out, guests)
        if bk_results:
            for item in bk_results: item['source'] = 'Booking.com'
            all_accommodations.extend(bk_results)
    except Exception as e: print(f"Booking.com Error: {e}")

    # (C) Amadeus
    try:
        am_results = search_amadeus(destination, check_in, check_out, guests)
        if am_results:
            for item in am_results: item['source'] = 'Amadeus'
            all_accommodations.extend(am_results)
    except Exception as e: print(f"Amadeus Error: {e}")

    ## LLM에 전달할 텍스트 구성
    if all_accommodations:
        # 상위 10개 정도만 추려서 텍스트화
        raw_text = "\n".join([
            f"- [{h.get('source')}] {h.get('name')}: {h.get('price')} (평점: {h.get('rating')})" 
            for h in all_accommodations[:10]
        ])
    else:
        raw_text = "현재 실시간 검색 결과가 없습니다. 일반적인 숙소 예약 팁을 알려주세요."

    system_msg = "전문 호텔 컨시어지로서, 검색된 목록을 비교하여 최적의 숙소를 추천하세요. 만약 데이터가 없다면 해당 지역의 숙소 예약 전략을 안내하세요."
    user_msg = f"사용자 요청: {user_message}\n\n[통합 숙소 데이터]\n{raw_text}"

    return call_gemini(system_msg, user_msg)


# -------------------------------------------------------------------
# 5. 맛집/명소 검색
# -------------------------------------------------------------------
def run_food_spot_search_tool(user_message: str, context: str) -> str:
    print("RUNNING: Food/Spot Search")
    
    param_prompt = """
    추출 'query' (검색어)와 'place_type' (restaurant 또는 tourist_attraction).
    JSON: {"query": "상하이 맛집", "place_type": "restaurant"}
    """
    params = extract_params_with_openai(param_prompt, user_message, context)
    query = params.get("query", "")
    
    g_results = search_places_google(query, params.get("place_type"), min_rating=4.0)
    
    data_text = ""
    if g_results:
        data_text = "[Google Maps]\n" + "\n".join([f"{p['name']} (★{p['rating']})" for p in g_results])
    else:
        n_results = search_places_naver(query)
        data_text = "[Naver Maps]\n" + "\n".join([f"{p['title']} ({p['category']})" for p in n_results])

    return call_gemini("당신은 미식 가이드입니다.", f"요청: {user_message}\n데이터:\n{data_text}")

# -------------------------------------------------------------------
# [NEW] 6. 축제/이벤트 검색
# -------------------------------------------------------------------

# tools.py 내 run_event_search_tool 함수 부분

def run_event_search_tool(user_message: str, context: str) -> str:
    print("RUNNING: Unified Event/Festival/Culture Search (Domestic & International)")
    
    current_year = datetime.now().year
    
    # 1. OpenAI를 통해 검색에 필요한 파라미터(국가, 지역, 검색어, 날짜) 추출
    param_prompt = f"""
    사용자의 요청에서 축제, 행사, 전시회 검색을 위한 파라미터를 추출하세요. 현재 연도는 {current_year}년입니다.
    - country: "한국" 또는 "해외" (질문 맥락에 따라 판단)
    - region: 도시나 지역명 (예: 서울, 부산, 파리, 삿포로)
    - query: 검색어 (구글 검색용 풀 텍스트, 예: "부산 벚꽃 축제", "Paris fashion week")
    - start_date: 행사 시작 기준일 (YYYY-MM-DD 형식, 모르면 빈 문자열 "")
    
    JSON 형식으로만 출력: {{"country": "한국", "region": "서울", "query": "서울 전시회", "start_date": ""}}
    """
    params = extract_params_with_openai(param_prompt, user_message, context)
    
    country = params.get("country", "한국")
    region = params.get("region", "")
    query = params.get("query", "축제")
    start_date = params.get("start_date", "")
    
    events = []
    source_name = ""

    # 2. 국가 판별에 따른 API 분기 실행
    if country == "한국":
        # event_service.py에서 정의한 통합 함수 호출 (축제 + 문화시설)
        events = search_korea_festivals_tourapi(region=region, start_date=start_date)
        source_name = "한국관광공사(TourAPI)"
    else:
        # 해외인 경우 기존 SerpAPI 호출
        events = search_events_serpapi(query)
        source_name = "구글 이벤트(SerpAPI)"
    
    # 3. 데이터 텍스트화 (두 API의 응답 형식을 고려하여 통합 포맷팅)
    if events:
        data_text = f"🔎 [{source_name} 검색 결과]\n"
        for idx, ev in enumerate(events[:10], 1): # 최대 10개 표시
            # 각 API마다 key 값이 조금씩 다를 수 있으므로 안전하게 get 사용
            title = ev.get('title', '제목 없음')
            date = ev.get('date', '날짜 정보 없음')
            address = ev.get('address', '위치 정보 없음')
            description = ev.get('description', '')
            link = ev.get('link', '')
            etype = ev.get('type', '이벤트') # TourAPI에는 type 정보가 있음

            data_text += f"{idx}. [{etype}] {title}\n"
            data_text += f"   📅 일정: {date}\n"
            data_text += f"   📍 위치: {address}\n"
            
            if description and description != "설명 없음":
                data_text += f"   💬 {description}\n"
            
            if link: # SerpAPI 등 링크가 있는 경우 표시
                data_text += f"   🔗 링크: {link}\n"
                
            data_text += "-" * 30 + "\n"
    else:
        data_text = f"현재 {region if region else country} 지역의 검색된 정보가 없습니다."

    # 4. Gemini에게 데이터를 전달하여 최종 답변 생성
    system_prompt = "당신은 국내외 축제, 전시, 문화 행사를 꿰뚫고 있는 전문 여행 가이드입니다. 제공된 데이터를 바탕으로 사용자에게 친절하고 상세하게 추천해 주세요."
    user_prompt = f"사용자 요청: {user_message}\n\n[검색된 실시간 데이터 리스트]\n{data_text}\n\n위 데이터를 분석하여 사용자의 요청에 딱 맞는 추천 답변을 작성해 주세요."
    
    return call_gemini(system_prompt, user_prompt, temperature=0.5)
#-----------------------------------------------------------------
# 7. [NEW] 현지 가이드 (실시간 교통 길찾기 연동 - 대중교통 & 자동차)
# -------------------------------------------------------------------
def run_local_guide_tool(user_message: str, context: str) -> str:
    print("RUNNING: Local Guide (With Live Transit & Driving)")
    
    # 사용자가 특정 장소 간의 이동 방법을 물어봤는지 파악
    param_prompt = """
    사용자의 요청이 'A에서 B로 가는 방법'처럼 특정 경로의 교통편을 묻는 것이라면 출발지와 도착지를 추출하세요.
    경로 질문이 아니면 빈 문자열을 반환하세요.
    JSON: {"origin": "신주쿠역", "destination": "시부야 스카이"}
    """
    params = extract_params_with_openai(param_prompt, user_message, context)
    origin = params.get("origin")
    dest = params.get("destination")
    
    transit_data = ""
    # 출발지/도착지가 모두 있으면 실시간 구글 맵스 API 호출 (대중교통 & 자동차 둘 다)
    if origin and dest:
        print(f"🚌/🚗 대중교통/자동차 실시간 경로 검색: {origin} -> {dest}")
        transit_result = get_directions_info(origin, dest, mode="transit")
        driving_result = get_directions_info(origin, dest, mode="driving")
        transit_data = f"\\n[실시간 대중교통 데이터: {origin} -> {dest}]\\n{transit_result}\\n\\n[실시간 자동차(택시/렌트카) 데이터: {origin} -> {dest}]\\n{driving_result}\\n"

    system_prompt = "당신은 빠삭한 현지 지식을 갖춘 교통/로컬 가이드입니다."
    user_prompt = f"""
    [대화 맥락] {context}
    [사용자 질문] {user_message}
    {transit_data}
    
    위 데이터를 바탕으로 이동 방법(대중교통, 자동차 등)이나 현지 꿀팁(패스권 추천, 도로 상황, 대중교통 주의사항 등)을 상세하고 친절하게 안내해 주세요. 제공된 대중교통 시간과 자동차 시간이 둘다 있다면 비교해서 가장 좋은 방법을 추천해 주세요.
    """
    return call_gemini(system_prompt, user_prompt, temperature=0.3)

# -------------------------------------------------------------------
# 8. 교통 수단 검색
# -------------------------------------------------------------------
def transportation_search(args: dict, context: str = "") -> str:
    """
    A -> B 단일 구간 이동 옵션 검색
    args:
      - origin (str)
      - destination (str)
      - mode (str, optional): TRANSIT/WALK/DRIVE/BICYCLE/ALL or 한국어 별칭(도보/대중교통/자동차/전체)
      - modes (list[str], optional): ["TRANSIT","WALK","DRIVE"] 처럼 명시 (mode보다 우선순위 낮게)
      - departure_time_iso (str, optional)
    """
    args = args or {}
    origin = (args.get("origin") or "").strip()
    destination = (args.get("destination") or "").strip()

    if not origin or not destination:
        return (
            "이동 경로를 찾기 위해 출발지(origin)와 도착지(destination)가 필요해요.\n"
            "예) '도쿄역에서 시부야 스크램블까지 대중교통으로 얼마나 걸려?'"
        )

    mode = args.get("mode")
    modes = args.get("modes")
    departure_time_iso = args.get("departure_time_iso")

    return render_transport_options(
        origin=origin,
        destination=destination,
        mode=mode,
        modes=modes,
        departure_time_iso=departure_time_iso,
    )


def transportation_batch(args: dict, context: str = "") -> str:
    """
    일정(장소 리스트)의 인접 구간 이동시간을 한 번에 계산
    args:
      - stops (list[str])  # ["도쿄역","센소지","시부야"] ...
      - mode (str, optional): TRANSIT/WALK/DRIVE/BICYCLE (ALL은 TRANSIT으로 처리됨)
      - departure_time_iso (str, optional)
    """
    args = args or {}
    stops = args.get("stops") or []
    if isinstance(stops, str):
        # 혹시 문자열로 오면 쉼표로 분해
        stops = [s.strip() for s in stops.split(",") if s.strip()]

    if not isinstance(stops, list) or len(stops) < 2:
        return (
            "구간별 이동시간을 계산하려면 stops에 최소 2개 이상의 장소가 필요해요.\n"
            "예) stops=['도쿄역','센소지','아키하바라','시부야']"
        )

    mode = args.get("mode") or "TRANSIT"
    departure_time_iso = args.get("departure_time_iso")

    return render_transport_batch(
        stops=stops,
        mode=mode,
        departure_time_iso=departure_time_iso,
    )
# -------------------------------------------------------------------
# 메인 라우터
# -------------------------------------------------------------------
def run_tools_from_plan(plan: Dict[str, Any], context: str) -> str:
    plan = plan or {}
    tool = plan.get("tools", ["general_chat"])[0]
    user_message = plan.get("original_user_message", "")

    args = plan.get("args") or {}

    print(f"🚀 [Tool Execution] Tool: {tool}")

    if tool == "trip_ideation":
        return run_trip_ideation_tool(user_message, context)
    elif tool == "itinerary_planner":
        return run_itinerary_planner_tool(user_message, context)
    elif tool == "flight_search":
        return run_flight_search_tool(user_message, context)
    elif tool in ["stay_search", "accommodation_booking"]:
        return run_stay_search_tool(user_message, context)
    elif tool == "food_spot_search":
        return run_food_spot_search_tool(user_message, context)
    elif tool == "event_search":
        return run_event_search_tool(user_message, context)
    elif tool == "transportation_search":
        args = plan.get("args", {}) or {}
        return transportation_search(args, context)
    elif tool == "transportation_batch":
        args = plan.get("args", {}) or {}
        return transportation_batch(args, context)
    elif tool == "local_guide":
        return run_local_guide_tool(user_message, context)
    elif tool == "budget_planner":
        return call_gemini("예산 전문가입니다.", f"컨텍스트: {context}\n질문: {user_message}")
    elif tool == "out_of_scope":
        return "여행과 관련된 질문을 해주시면 기쁘게 도와드릴 수 있습니다! 😊"
    else:
        return call_gemini("친절한 여행 에이전트입니다.", f"{context}\nUser: {user_message}")
