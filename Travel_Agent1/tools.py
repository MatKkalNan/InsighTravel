import os
import json
from datetime import datetime
from typing import Dict, Any, List

from dotenv import load_dotenv
from openai import OpenAI

# [서비스 모듈 임포트]
from naver_service import search_places_naver
from google_maps_service import search_places_google
from crawl_accommodation import search_hotels_api
from flight_service import search_flight_offers

# [Gemini 서비스 임포트]
from gemini_service import call_gemini, summarize_flight_data

# [변경] 프롬프트 모듈 임포트
from prompts.tools_prompts import (
    get_ideation_prompt,
    ITINERARY_PARAM_SYSTEM, get_itinerary_prompt,
    get_flight_param_system,
    STAY_PARAM_SYSTEM, get_stay_prompt,
    FOOD_SPOT_PARAM_SYSTEM, get_food_spot_prompt
)

load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


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
    # [변경] 하드코딩 제거
    user_prompt = get_ideation_prompt(user_message, context)
    return call_gemini("당신은 창의적인 '여행 큐레이터'입니다.", user_prompt, temperature=0.7)


# -------------------------------------------------------------------
# 2. 일정 플래너 (OpenAI 추출 -> 지도 API -> Gemini 작성)
# -------------------------------------------------------------------
def run_itinerary_planner_tool(user_message: str, context: str) -> str:
    print("RUNNING: Itinerary Planner")
    
    # [변경] 하드코딩 제거 -> 프롬프트 모듈 사용
    params = extract_params_with_openai(ITINERARY_PARAM_SYSTEM, user_message, context)
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

    # [변경] 하드코딩 제거
    user_prompt = get_itinerary_prompt(user_message, places_info)
    return call_gemini("당신은 꼼꼼한 '여행 일정 플래너'입니다.", user_prompt, temperature=0.4)


# -------------------------------------------------------------------
# 3. 항공권 검색 (개선됨: 400 에러 방지 로직 추가)
# -------------------------------------------------------------------
def run_flight_search_tool(user_message: str, context: str) -> str:
    print("RUNNING: Flight Search")
    
    # 1. GPT: 파라미터 추출 (좌석, 직항 여부 등 포함)
    param_prompt = get_flight_param_system()
    params = extract_params_with_openai(param_prompt, user_message, context)
    
    origin = params.get("origin", "ICN")
    dest = params.get("destination")
    dep_date = params.get("departureDate")
    ret_date = params.get("return_date")
    
    # 추가 옵션 추출
    travel_class = params.get("travelClass")  # 예: ECONOMY, BUSINESS
    non_stop = params.get("nonStop")          # 예: True/False
    
    # 필수 파라미터 검증
    if not dest or not dep_date:
        return "출발지와 목적지, 날짜를 정확히 알려주시면 항공권을 찾아드릴게요."

    print(f"✈️ API 호출 파라미터: {origin}->{dest} ({dep_date}), 좌석:{travel_class}, 직항:{non_stop}")

    # 2. API: 데이터 수집 (옵션 전달)
    try:
        # flight_service.py의 search_flight_offers 함수는 **kwargs로 옵션을 받음
        flight_data = search_flight_offers(
            origin=origin, 
            destination=dest, 
            date=dep_date, 
            return_date=ret_date,
            travelClass=travel_class, # 좌석 등급 전달
            nonStop=non_stop          # 직항 여부 전달
        )
    except Exception as e:
        flight_data = f"항공권 검색 중 시스템 오류가 발생했습니다: {e}"

    # 3. Gemini: 요약 (gemini_service 내부 함수 사용)
    return summarize_flight_data(user_message, flight_data)

# -------------------------------------------------------------------
# 4. 숙소 검색
# -------------------------------------------------------------------
def run_stay_search_tool(user_message: str, context: str) -> str:
    print("RUNNING: Stay Search")
    
    # [변경] 하드코딩 제거
    params = extract_params_with_openai(STAY_PARAM_SYSTEM, user_message, context)
    
    accom_data = []
    if params.get("destination"):
        # crawl_accommodation.py 호출
        accom_data = search_hotels_api(
            params["destination"], params.get("check_in"), params.get("check_out"), params.get("guests", 2)
        )
    
    if accom_data:
        raw_text = "\n".join([f"{h['name']} - {h['price']} ({h['rating']})" for h in accom_data[:10]])
    else:
        raw_text = "조건에 맞는 숙소를 찾지 못했습니다."

    # [변경] 하드코딩 제거
    user_prompt = get_stay_prompt(user_message, raw_text)
    return call_gemini("당신은 친절한 '호텔 컨시어지'입니다.", user_prompt)


# -------------------------------------------------------------------
# 5. 맛집/명소 검색
# -------------------------------------------------------------------
def run_food_spot_search_tool(user_message: str, context: str) -> str:
    print("RUNNING: Food/Spot Search")
    
    # [변경] 하드코딩 제거
    params = extract_params_with_openai(FOOD_SPOT_PARAM_SYSTEM, user_message, context)
    query = params.get("query", "")
    
    g_results = search_places_google(query, params.get("place_type"), min_rating=4.0)
    
    data_text = ""
    if g_results:
        data_text = "[Google Maps]\n" + "\n".join([f"{p['name']} (★{p['rating']})" for p in g_results])
    else:
        n_results = search_places_naver(query)
        data_text = "[Naver Maps]\n" + "\n".join([f"{p['title']} ({p['category']})" for p in n_results])

    # [변경] 하드코딩 제거
    user_prompt = get_food_spot_prompt(user_message, data_text)
    return call_gemini("당신은 '현지 미식 가이드'입니다.", user_prompt)


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
        return call_gemini("당신은 '현지 가이드'입니다.", f"컨텍스트: {context}\n질문: {user_message}")
    elif tool == "budget_planner":
        return call_gemini("당신은 '예산 전문가'입니다.", f"컨텍스트: {context}\n질문: {user_message}")
    elif tool == "out_of_scope":
        return "여행과 관련된 질문을 해주시면 기쁘게 도와드릴 수 있습니다!"
    else:
        return call_gemini("당신은 '친절한 여행 에이전트'입니다.", f"{context}\nUser: {user_message}")