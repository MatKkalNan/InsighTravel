# tools.py
import os
import json
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

load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


# -------------------------------------------------------------------
# [Helper] OpenAI를 이용한 '정확한' 파라미터 추출 (논리적 작업)
# -------------------------------------------------------------------
def extract_params_with_openai(system_prompt: str, user_message: str, context: str) -> Dict[str, Any]:
    """OpenAI(GPT-4o/Turbo)를 사용하여 JSON 파라미터만 정확히 추출"""
    try:
        resp = client.chat.completions.create(
            model="gpt-4-turbo",  # 또는 gpt-3.5-turbo
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
    # 창작/작성은 Gemini에게 위임
    return call_gemini(system_prompt, user_prompt, temperature=0.7)


# -------------------------------------------------------------------
# 2. 일정 플래너 (OpenAI 추출 -> 지도 API -> Gemini 작성)
# -------------------------------------------------------------------
def run_itinerary_planner_tool(user_message: str, context: str) -> str:
    print("RUNNING: Itinerary Planner")
    
    # 1) OpenAI로 도시 및 한국 여부 판단
    param_prompt = """
    Extract 'destination' and 'is_korea'(boolean).
    JSON: {"destination": "Jeju", "is_korea": true}
    """
    params = extract_params_with_openai(param_prompt, user_message, context)
    destination = params.get("destination", "여행지")
    is_korea = params.get("is_korea", False)

    # 2) 지도 데이터 수집 (Google Maps + Naver)
    places_info = ""
    print(f"🔎 '{destination}' 장소 검색 중... (한국여부: {is_korea})")
    
    # 구글 맵 (평점 4.0 이상)
    g_spots = search_places_google(f"{destination} tourist attraction", "tourist_attraction", min_rating=4.0)
    g_food = search_places_google(f"{destination} restaurant", "restaurant", min_rating=4.0)
    
    if g_spots or g_food:
        places_info += f"\n[Google Maps Data for {destination}]\n"
        for p in g_spots[:5]: places_info += f"- (명소) {p['name']} (★{p['rating']}, 리뷰 {p['user_ratings_total']})\n"
        for p in g_food[:5]: places_info += f"- (맛집) {p['name']} (★{p['rating']}, 리뷰 {p['user_ratings_total']})\n"

    # 한국일 경우 네이버 보완 (Google 결과가 적거나 없을 때 유용)
    if is_korea:
        n_spots = search_places_naver(f"{destination} 가볼만한곳")
        n_food = search_places_naver(f"{destination} 맛집")
        if n_spots or n_food:
            places_info += f"\n[Naver Maps Data (Backup)]\n"
            for p in n_spots[:5]: places_info += f"- (명소) {p['title']}\n"
            for p in n_food[:5]: places_info += f"- (맛집) {p['title']}\n"

    # 3) Gemini로 일정표 작성
    system_prompt = "당신은 전문 여행 플래너입니다. 동선과 장소의 매력을 고려하여 완벽한 일정을 계획합니다."
    user_prompt = f"""
    [사용자 요청] {user_message}
    [검색된 장소 데이터] {places_info}
    
    위 데이터를 적극 활용하여 실현 가능한 일정을 짜주세요.
    - 데이터에 있는 장소(Google/Naver)를 우선적으로 포함하세요.
    - 장소 이름 뒤에 괄호로 별점이나 특징을 적어주세요.
    """
    return call_gemini(system_prompt, user_prompt, temperature=0.4)


# -------------------------------------------------------------------
# 3. 항공권 검색 (OpenAI 추출 -> Amadeus API -> Gemini 요약)
# -------------------------------------------------------------------
def run_flight_search_tool(user_message: str, context: str) -> str:
    print("RUNNING: Flight Search")
    
    # 1) OpenAI로 파라미터 추출
    param_prompt = """
    Extract flight params: origin(code), destination(code), departureDate(YYYY-MM-DD), returnDate.
    Example JSON: {"origin": "ICN", "destination": "NRT", "departureDate": "2024-05-01", "returnDate": null}
    """
    params = extract_params_with_openai(param_prompt, user_message, context)
    
    # 2) API 호출
    flight_data = "검색 조건을 명확히 알 수 없어 항공권을 찾지 못했습니다."
    if params.get("origin") and params.get("destination"):
        try:
            flight_data = search_flight_offers(
                params["origin"], params["destination"], params["departureDate"], params.get("returnDate")
            )
        except Exception as e:
            flight_data = f"오류 발생: {str(e)}"

    # 3) Gemini 요약 (전용 함수 활용)
    return summarize_flight_data(user_message, flight_data)


# -------------------------------------------------------------------
# 4. 숙소 검색 (OpenAI 추출 -> Amadeus API -> Gemini 요약)
# -------------------------------------------------------------------
def run_stay_search_tool(user_message: str, context: str) -> str:
    print("RUNNING: Stay Search")
    
    # 1) OpenAI 파라미터
    param_prompt = """
    Extract: destination, check_in(YYYY-MM-DD), check_out, guests(int).
    JSON: {"destination": "Seoul", "check_in": "...", "check_out": "...", "guests": 2}
    """
    params = extract_params_with_openai(param_prompt, user_message, context)
    
    # 2) API 호출
    accom_data = []
    if params.get("destination"):
        accom_data = search_hotels_api(
            params["destination"], params.get("check_in"), params.get("check_out"), params.get("guests", 2)
        )
    
    # 데이터 텍스트 변환
    if accom_data:
        raw_text = "\n".join([f"{h['name']} - {h['price']} ({h['rating']})" for h in accom_data[:10]])
    else:
        raw_text = "조건에 맞는 숙소를 API에서 찾지 못했습니다."

    # 3) Gemini 추천
    system_prompt = "당신은 호텔 컨시어지입니다."
    user_prompt = f"""
    [사용자 선호] {user_message}
    [검색된 호텔 목록]
    {raw_text}
    
    목록 중에서 사용자에게 적합한 호텔 3~5곳을 추천하고, 가격과 특징을 깔끔하게 정리해 주세요.
    """
    return call_gemini(system_prompt, user_prompt, temperature=0.4)


# -------------------------------------------------------------------
# 5. 맛집/명소 검색 (OpenAI 추출 -> Google/Naver -> Gemini)
# -------------------------------------------------------------------
def run_food_spot_search_tool(user_message: str, context: str) -> str:
    print("RUNNING: Food/Spot Search")
    
    # 1) OpenAI 파라미터
    param_prompt = """
    Extract 'query' and 'place_type' for Google Maps.
    JSON: {"query": "강남역 파스타", "place_type": "restaurant"}
    """
    params = extract_params_with_openai(param_prompt, user_message, context)
    query = params.get("query", "")
    
    # 2) API 검색
    g_results = search_places_google(query, params.get("place_type"), min_rating=4.0)
    
    # Google 결과 없으면 Naver 시도
    data_text = ""
    if g_results:
        data_text = "[Google Maps]\n" + "\n".join([f"{p['name']} (★{p['rating']})" for p in g_results])
    else:
        n_results = search_places_naver(query)
        data_text = "[Naver Maps]\n" + "\n".join([f"{p['title']} ({p['category']})" for p in n_results])

    # 3) Gemini 요약
    return call_gemini(
        "당신은 미식 가이드입니다.",
        f"사용자 질문: {user_message}\n검색 결과:\n{data_text}\n\n결과를 바탕으로 추천 장소를 소개해 주세요."
    )


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
        return call_gemini("현지 가이드입니다.", f"{context}\n질문: {user_message}")
    elif tool == "budget_planner":
        return call_gemini("예산 설계 전문가입니다.", f"{context}\n질문: {user_message}")
    elif tool == "out_of_scope":
        return "죄송합니다. 저는 여행 도우미라 그 주제는 답변하기 어렵습니다."
    else:
        # 일반 대화 -> Gemini
        return call_gemini("당신은 친절한 여행 에이전트입니다.", f"{context}\nUser: {user_message}")
