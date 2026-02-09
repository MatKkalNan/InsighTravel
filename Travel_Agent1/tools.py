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
from google_maps_service import search_places_google
from crawl_accommodation_tripadvisor import search_hotels_with_retry as search_tripadvisor
from crawl_accommodation_booking_com import search_hotels_api as search_booking
from crawl_accommodation_amadeus import search_hotels_api as search_amadeus
from flight_service import search_flight_offers  

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

    system_prompt = "당신은 전문 여행 플래너입니다. 동선과 장소의 매력을 고려하여 완벽한 일정을 계획합니다."
    user_prompt = f"""
    [사용자 요청] {user_message}
    [검색된 장소 데이터] {places_info}
    
    위 데이터를 활용하여 실현 가능한 일정을 짜주세요. 데이터에 있는 장소 이름을 우선적으로 사용하세요.
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
# 메인 라우터
# -------------------------------------------------------------------
def run_tools_from_plan(plan: Dict[str, Any], context: str) -> str:
    tool = plan.get("tools", ["general_chat"])[0]
    user_message = plan.get("original_user_message", "")

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
    elif tool == "local_guide":
        return call_gemini("현지 가이드입니다.", f"컨텍스트: {context}\n질문: {user_message}")
    elif tool == "budget_planner":
        return call_gemini("예산 전문가입니다.", f"컨텍스트: {context}\n질문: {user_message}")
    elif tool == "out_of_scope":
        return "여행과 관련된 질문을 해주시면 기쁘게 도와드릴 수 있습니다! 😊"
    else:
        return call_gemini("친절한 여행 에이전트입니다.", f"{context}\nUser: {user_message}")