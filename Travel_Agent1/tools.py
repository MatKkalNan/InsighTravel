# tools.py
import os
import re
import json
from datetime import datetime
from typing import Dict, Any, List, Optional

from dotenv import load_dotenv
from openai import OpenAI

from datetime import datetime, date

def _today() -> date:
    return datetime.now().date()

def _parse_yyyy_mm_dd(value: Any) -> Optional[date]:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        return datetime.strptime(text, "%Y-%m-%d").date()
    except Exception:
        return None

def _to_iso(d: Optional[date]) -> Optional[str]:
    return d.isoformat() if d else None

def _normalize_guests(value: Any, default: int = 2) -> int:
    if value is None:
        return default

    if isinstance(value, int):
        return max(1, value)

    raw = str(value).strip()
    if raw in ["혼자", "1명", "한 명", "1"]:
        return 1
    if raw in ["둘", "2명", "두 명", "2", "미정", ""]:
        return 2

    digits = re.sub(r"[^\d]", "", raw)
    if digits:
        try:
            return max(1, int(digits))
        except Exception:
            return default

    return default

def _validate_future_date(d: Optional[date]) -> bool:
    return d is not None and d >= _today()

def _validate_date_range(start_date: Optional[date], end_date: Optional[date]) -> bool:
    if start_date is None or end_date is None:
        return False
    if start_date < _today():
        return False
    if end_date <= start_date:
        return False
    return True

def _safe_int(value: Any, default: int = 0) -> int:
    try:
        if value is None or value == "":
            return default
        return int(value)
    except Exception:
        return default

# [✨ 핵심: prompts.py에서 모든 프롬프트 가져오기]
from prompts import *

# [서비스 모듈 임포트]
from naver_service import search_places_naver
from google_maps_service import search_places_google, get_directions_info
from crawl_accommodation_tripadvisor import search_hotels_with_retry as search_tripadvisor
from crawl_accommodation_booking_com import search_hotels_api as search_booking
from crawl_accommodation_amadeus import search_hotels_api as search_amadeus
from flight_service import search_flight_offers
from transportation_service import render_transport_options, render_transport_batch
from event_service import search_events_serpapi, search_korea_festivals_tourapi
from travel_warning_service import render_travel_warning

# [Gemini 서비스 임포트]
from gemini_service import call_gemini, summarize_flight_data

# [예약 기능]
from booking_page_service import booking_store

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
def run_trip_ideation_tool(user_message: str, context: str, survey: dict = None) -> str:
    user_prompt = build_ideation_user_prompt(context, user_message, survey=survey)
    return call_gemini(IDEATION_SYSTEM, user_prompt, temperature=0.7)


# -------------------------------------------------------------------
# 2. 일정 플래너 (OpenAI 추출 -> 지도 API -> Gemini 작성)
# -------------------------------------------------------------------
def run_itinerary_planner_tool(user_message: str, context: str, weather_data=None, survey: dict = None) -> str:
    print("RUNNING: Itinerary Planner")
    
    # 1. 파라미터 추출
    params = extract_params_with_openai(ITINERARY_PARAM_PROMPT, user_message, context)
    destination = params.get("destination", "여행지")
    is_korea = params.get("is_korea", False)

    # 2. 장소 검색 (Google/Naver)
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
            
    # 3. 날씨 데이터 처리
    weather_info_text = ""
    if weather_data:
        weather_info_text = f"\n[실시간 날씨 데이터]\n{json.dumps(weather_data, ensure_ascii=False, indent=2)}"

    # 4. 최종 프롬프트 구성 및 Gemini 호출
   #user_prompt = build_itinerary_user_prompt(user_message, places_info, weather_info_text, survey=survey)
    # 4. 최종 프롬프트 구성 및 Gemini 호출
    user_prompt = build_itinerary_user_prompt(context, user_message, places_info, weather_info_text, survey=survey)
    return call_gemini(ITINERARY_SYSTEM, user_prompt, temperature=0.4)
    #return call_gemini(ITINERARY_SYSTEM, user_prompt, temperature=0.4)


# -------------------------------------------------------------------
# 3. 항공권 검색
# -------------------------------------------------------------------
def run_flight_search_tool(user_message: str, context: str, survey: dict = None) -> str:
    print("RUNNING: Flight Search")

    param_prompt = build_flight_param_prompt()
    params = extract_params_with_openai(param_prompt, user_message, context)
    print("[DEBUG] flight params extracted:", params)

    origin = (params.get("origin") or "ICN").strip()
    dest = (params.get("destination") or "").strip()

    dep_date_str = (params.get("departureDate") or "").strip()
    ret_date_str = (params.get("return_date") or "").strip()

    dep_date_obj = _parse_yyyy_mm_dd(dep_date_str)
    ret_date_obj = _parse_yyyy_mm_dd(ret_date_str) if ret_date_str else None

    if not dest:
        return "목적지 정보가 부족해서 항공권을 검색할 수 없어요. 예: 다음주 오사카 항공권 알려줘"

    if not _validate_future_date(dep_date_obj):
        return "출국 날짜를 다시 알려주세요. YYYY-MM-DD 형식의 미래 날짜가 필요해요."

    if ret_date_str and ret_date_obj is None:
        return "귀국 날짜 형식이 올바르지 않아요. YYYY-MM-DD 형식으로 다시 알려주세요."

    if ret_date_obj and ret_date_obj <= dep_date_obj:
        return "귀국 날짜는 출국 날짜보다 뒤여야 해요."

    dep_date = _to_iso(dep_date_obj)
    ret_date = _to_iso(ret_date_obj)

    print(f"✈️ API 호출 파라미터: {origin} -> {dest}, 날짜: {dep_date}, 귀국: {ret_date}")

    try:
        flight_data = search_flight_offers(origin, dest, dep_date, ret_date)
    except Exception as e:
        flight_data = f"항공권 검색 중 API 오류가 발생했습니다: {str(e)}"

    return summarize_flight_data(user_message, flight_data, survey=survey)


# -------------------------------------------------------------------
# 4. 숙소 검색
# -------------------------------------------------------------------
def run_stay_search_tool(user_message: str, context: str, survey: dict = None) -> str:
    print("RUNNING: Stay Search")

    params = extract_params_with_openai(STAY_PARAM_PROMPT, user_message, context)
    print("[DEBUG] stay params extracted:", params)

    destination = (params.get("destination") or "").strip()
    guests = _normalize_guests(params.get("guests"), default=2)

    check_in_str = (params.get("check_in") or "").strip()
    check_out_str = (params.get("check_out") or "").strip()

    check_in_obj = _parse_yyyy_mm_dd(check_in_str)
    check_out_obj = _parse_yyyy_mm_dd(check_out_str)

    print("[DEBUG] normalized stay params:", {
        "destination": destination,
        "check_in": check_in_str,
        "check_out": check_out_str,
        "check_in_valid": _validate_future_date(check_in_obj),
        "check_out_valid": check_out_obj is not None,
        "guests": guests,
    })

    if not destination:
        return "어느 지역의 숙소를 찾아드릴까요? 도시 이름을 말씀해 주세요."

    if not _validate_future_date(check_in_obj):
        return "체크인 날짜를 다시 알려주세요. 미래 날짜가 필요해요."

    if not _validate_date_range(check_in_obj, check_out_obj):
        return "체크아웃 날짜를 다시 알려주세요. 체크아웃은 체크인보다 뒤여야 해요."

    check_in = _to_iso(check_in_obj)
    check_out = _to_iso(check_out_obj)

    all_accommodations = []

    try:
        ta_results = search_tripadvisor(destination, check_in, check_out)
        if ta_results:
            for item in ta_results:
                item["source"] = "TripAdvisor"
            all_accommodations.extend(ta_results)
    except Exception as e:
        print(f"TripAdvisor Error: {e}")

    try:
        bk_results = search_booking(destination, check_in, check_out, guests)
        if bk_results:
            for item in bk_results:
                item["source"] = "Booking.com"
            all_accommodations.extend(bk_results)
    except Exception as e:
        print(f"Booking.com Error: {e}")

    try:
        am_results = search_amadeus(destination, check_in, check_out, guests)
        if am_results:
            for item in am_results:
                item["source"] = "Amadeus"
            all_accommodations.extend(am_results)
    except Exception as e:
        print(f"Amadeus Error: {e}")

    if all_accommodations:
        raw_text = "\n".join([
            f"- [{h.get('source')}] {h.get('name')}: {h.get('price')} (평점: {h.get('rating')})"
            for h in all_accommodations[:10]
        ])
    else:
        raw_text = "현재 실시간 검색 결과가 없습니다. 일반적인 숙소 예약 팁을 알려주세요."

    user_prompt = build_stay_user_prompt(user_message, raw_text, survey=survey)
    return call_gemini(STAY_SYSTEM, user_prompt)


# -------------------------------------------------------------------
# 5. 맛집/명소 검색
# -------------------------------------------------------------------
def run_food_spot_search_tool(user_message: str, context: str, survey: dict = None) -> str:
    print("RUNNING: Food/Spot Search")
    
    params = extract_params_with_openai(FOOD_PARAM_PROMPT, user_message, context)
    query = params.get("query", "")
    
    g_results = search_places_google(query, params.get("place_type"), min_rating=4.0)
    
    data_text = ""
    if g_results:
        data_text = "[Google Maps]\n" + "\n".join([f"{p['name']} (★{p['rating']})" for p in g_results])
    else:
        n_results = search_places_naver(query)
        data_text = "[Naver Maps]\n" + "\n".join([f"{p['title']} ({p['category']})" for p in n_results])

    user_prompt = build_food_user_prompt(user_message, data_text, survey=survey)
    return call_gemini(FOOD_SYSTEM, user_prompt)

# -------------------------------------------------------------------
# 6. 축제/이벤트 검색
# -------------------------------------------------------------------
def run_event_search_tool(user_message: str, context: str) -> str:
    print("RUNNING: Unified Event/Festival/Culture Search (Domestic & International)")
    
    param_prompt = build_event_param_prompt(context)
    params = extract_params_with_openai(param_prompt, user_message, context)
    print("[DEBUG] event params extracted:", params)
    
    country = params.get("country", "한국")
    region = params.get("region", "")
    query = params.get("query", "축제")
    start_date = params.get("start_date", "")

    events = []
    source_name = ""

    if country == "한국":
        events = search_korea_festivals_tourapi(region=region, start_date=start_date)
        source_name = "한국관광공사(TourAPI)"
    else:
        events = search_events_serpapi(query)
        source_name = "구글 이벤트(SerpAPI)"

    if events:
        data_text = f"[{source_name} 검색 결과]\n"
        for idx, ev in enumerate(events[:10], 1):
            title = ev.get("title", "제목 없음")
            date_text = ev.get("date", "날짜 정보 없음")
            address = ev.get("address", "위치 정보 없음")
            description = ev.get("description", "")
            link = ev.get("link", "")
            etype = ev.get("type", "이벤트")

            data_text += f"{idx}. [{etype}] {title}\n"
            data_text += f"일정: {date_text}\n"
            data_text += f"위치: {address}\n"
            if description and description != "설명 없음":
                data_text += f"설명: {description}\n"
            if link:
                data_text += f"링크: {link}\n"
            data_text += "------------------------------\n"
    else:
        data_text = f"현재 {region if region else country} 지역의 검색된 정보가 없습니다."

    user_prompt = build_event_user_prompt(user_message, data_text)
    return call_gemini(EVENT_SYSTEM, user_prompt, temperature=0.5)

# -------------------------------------------------------------------
# 7. 현지 가이드 (실시간 교통 길찾기 연동)
# -------------------------------------------------------------------
def run_local_guide_tool(user_message: str, context: str) -> str:
    print("RUNNING: Local Guide (With Live Transit & Driving)")
    
    params = extract_params_with_openai(LOCAL_GUIDE_PARAM_PROMPT, user_message, context)
    origin = params.get("origin")
    dest = params.get("destination")
    
    transit_data = ""
    if origin and dest:
        print(f"🚌/🚗 대중교통/자동차 실시간 경로 검색: {origin} -> {dest}")
        transit_result = get_directions_info(origin, dest, mode="transit")
        driving_result = get_directions_info(origin, dest, mode="driving")
        transit_data = f"\\n[실시간 대중교통 데이터: {origin} -> {dest}]\\n{transit_result}\\n\\n[실시간 자동차(택시/렌트카) 데이터: {origin} -> {dest}]\\n{driving_result}\\n"

    user_prompt = build_local_guide_user_prompt(context, user_message, transit_data)
    return call_gemini(LOCAL_GUIDE_SYSTEM, user_prompt, temperature=0.3)

# -------------------------------------------------------------------
# 8. 교통 수단 검색
# -------------------------------------------------------------------
def transportation_search(args: dict, context: str = "") -> str:
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
    args = args or {}
    stops = args.get("stops") or []
    if isinstance(stops, str):
        stops = [
            s.strip()
            for s in re.split(r",|→|->|/|>", stops)
            if s.strip()
        ]

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
# 9. 여행 주의 경보
# -------------------------------------------------------------------
def run_travel_warning_tool(user_message: str, context: str) -> str:
    country = user_message.strip()
    return render_travel_warning(country)


# -------------------------------------------------------------------
# 10. 예약 실행 (에이전트 모드 트리거) - ✅ 오류 수정 적용 완료
# -------------------------------------------------------------------
def run_booking_action_tool(user_message: str, context: str) -> str:
    print("RUNNING: Booking Action (Agent Mode)")

    param_prompt = build_booking_param_prompt()
    params = extract_params_with_openai(param_prompt, user_message, context)
    print(f"[DEBUG] booking params extracted: {params}")

    booking_type = params.get("booking_type", "hotel")

    if booking_type == "hotel" and any(w in user_message for w in ["비행기", "항공", "항공권", "편도", "왕복", "출국", "귀국"]):
        booking_type = "flight"

    destination = (params.get("destination") or "").strip()
    destination_kr = (params.get("destination_kr") or destination).strip()
    guests = _normalize_guests(params.get("guests"), default=2)
    
    # [수정포인트 1] 저장용 세션 아이디를 프론트엔드와 동일하게 고정
    session_id = "demo-session-1"

    raw_index = params.get("item_index")
    already_chosen = raw_index is not None
    item_index = _safe_int(raw_index, default=0)

    if booking_type == "hotel":
        check_in_str = (params.get("check_in") or "").strip()
        check_out_str = (params.get("check_out") or "").strip()

        check_in_obj = _parse_yyyy_mm_dd(check_in_str)
        check_out_obj = _parse_yyyy_mm_dd(check_out_str)

        if not destination:
            return "어느 지역 숙소를 예약할까요? 예: 오사카 호텔 예약해줘"

        if not _validate_future_date(check_in_obj):
            return "체크인 날짜를 다시 알려주세요. 미래 날짜가 필요해요."

        if not _validate_date_range(check_in_obj, check_out_obj):
            return "체크아웃 날짜를 다시 알려주세요. 체크아웃은 체크인보다 뒤여야 해요."

        check_in = _to_iso(check_in_obj)
        check_out = _to_iso(check_out_obj)

        all_hotels = []

        try:
            bk = search_booking(destination, check_in, check_out, guests)
            if bk:
                for h in bk:
                    h["source"] = "Booking.com"
                all_hotels.extend(bk)
        except Exception as e:
            print(f"Booking.com Error: {e}")

        try:
            am = search_amadeus(destination, check_in, check_out, guests)
            if am:
                for h in am:
                    h["source"] = "Amadeus"
                all_hotels.extend(am)
        except Exception as e:
            print(f"Amadeus Error: {e}")

        if not all_hotels:
            return (
                f"{destination_kr}에서 {check_in} ~ {check_out} 조건으로 예약 가능한 숙소를 찾지 못했어요. "
                "날짜나 지역을 조금 바꿔서 다시 시도해볼까요?"
            )

        # 호텔은 원래 List[Dict] 형태이므로 그대로 저장
        booking_store.save_temp_data(session_id, "hotel", all_hotels[:10])

        if already_chosen:
            chosen_name = (
                (all_hotels[item_index].get("name") or "")
                if 0 <= item_index < len(all_hotels) else ""
            )
            bot_message = f"{chosen_name or (destination_kr + ' 호텔')} 예약을 진행할게요."
        else:
            bot_message = f"{destination_kr} 숙소 검색이 완료됐어요. 예약할 숙소를 선택해 주세요."

        return json.dumps({
            "__booking_action__": True,
            "booking_type": "hotel",
            "item_index": item_index,
            "session_id": session_id,
            "needs_selection": not already_chosen,
            "prefill": {
                "checkin": check_in,
                "checkout": check_out,
                "guests": guests,
                "destination_kr": destination_kr,
            },
            "message": bot_message,
        }, ensure_ascii=False)

    else:
        origin = (params.get("origin") or "ICN").strip()
        dep_date_str = (params.get("departure_date") or "").strip()
        ret_date_str = (params.get("return_date") or "").strip()

        dep_date_obj = _parse_yyyy_mm_dd(dep_date_str)
        ret_date_obj = _parse_yyyy_mm_dd(ret_date_str) if ret_date_str else None

        if not destination:
            return "어느 지역으로 가는 항공권을 예약할까요? 예: 도쿄 항공권 예약해줘"

        if not _validate_future_date(dep_date_obj):
            return "출국 날짜를 다시 알려주세요. 미래 날짜가 필요해요."

        if ret_date_str and ret_date_obj is None:
            return "귀국 날짜 형식이 올바르지 않아요. YYYY-MM-DD 형식으로 다시 알려주세요."

        if ret_date_obj and ret_date_obj <= dep_date_obj:
            return "귀국 날짜는 출국 날짜보다 뒤여야 해요."

        dep_date = _to_iso(dep_date_obj)
        ret_date = _to_iso(ret_date_obj)

        try:
            flight_raw = search_flight_offers(origin, destination, dep_date, ret_date)
        except Exception as e:
            flight_raw = f"항공편 검색 오류: {e}"

        if not flight_raw or "조건에 맞는 항공권을 찾을 수 없습니다" in flight_raw:
            return (
                f"{origin} → {destination_kr} ({dep_date}"
                + (f" ~ {ret_date}" if ret_date else "")
                + ") 조건으로 예약 가능한 항공편을 찾지 못했어요. "
                "날짜나 목적지를 바꿔 다시 시도해볼까요?"
            )

        # [수정포인트 2] flight_raw(문자열)를 파싱하여 UI가 읽을 수 있는 배열(List)로 변환
        flight_list = []
        if isinstance(flight_raw, str):
            lines = flight_raw.split('\n')
            for line in lines:
                # '1. 🎫[Amadeus/일반석]...' 와 같이 번호로 시작하는 줄을 감지
                if re.match(r'^\d+\.', line):
                    # 가격 부분과 텍스트 부분 분리
                    parts = line.split('| 💰')
                    desc = parts[0].strip() if len(parts) > 0 else line
                    price = parts[1].strip() if len(parts) > 1 else "가격 정보 없음"
                    
                    airline_name = "검색된 항공편"
                    if "Amadeus" in desc: airline_name = "Amadeus 시스템 추천 항공편"
                    if "Google" in desc: airline_name = "Google Flights 추천 항공편"

                    flight_list.append({
                        "airline": airline_name,
                        "price": price,
                        "origin": origin,
                        "destination": destination,
                        "dep_time": dep_date,
                        "stops": "상세 내역 확인",
                        "raw_text": desc # 필요시 사용
                    })
        
        # 파싱 실패 혹은 리스트가 비어있을 경우를 대비한 안전 장치 (더미 데이터 삽입)
        if not flight_list:
            # 사용자가 선택한 item_index 만큼 에러가 나지 않도록 여유 있게 생성
            for i in range(max(5, item_index + 1)):
                flight_list.append({
                    "airline": f"{destination_kr}행 항공편 (선택)",
                    "price": "예약 페이지 참조",
                    "origin": origin,
                    "destination": destination,
                    "dep_time": dep_date,
                    "stops": "-"
                })

        # List[Dict] 형태로 데이터를 안전하게 저장
        booking_store.save_temp_data(session_id, "flight", flight_list)

        if already_chosen:
            bot_message = "항공편 예약을 진행할게요."
        else:
            bot_message = f"{destination_kr} 항공권 검색이 완료됐어요. 예약할 항공편을 선택해 주세요."

        return json.dumps({
            "__booking_action__": True,
            "booking_type": "flight",
            "item_index": item_index,
            "session_id": session_id,
            "needs_selection": not already_chosen,
            "prefill": {
                "departure_date": dep_date,
                "return_date": ret_date or "",
                "guests": guests,
                "origin": origin,
                "destination": destination,
                "destination_kr": destination_kr,
            },
            "message": bot_message,
        }, ensure_ascii=False)


def run_out_of_scope_tool(user_message: str, context: str = "") -> str:
    prompt = f"컨텍스트:\n{context}\n\n사용자 질문:\n{user_message}"
    try:
        return call_gemini(OUT_OF_SCOPE_SYSTEM, prompt)
    except Exception:
        return (
            "지금은 여행 관련 질문에 맞춰 도와드리고 있어요. "
            "원하시면 여행지 추천이나 일정, 숙소·항공권 쪽으로 이어서 도와드릴게요."
        )

# -------------------------------------------------------------------
# 메인 라우터
# -------------------------------------------------------------------
def run_tools_from_plan(
    plan: Dict[str, Any],
    context: str,
    weather_data: Optional[dict] = None,
    long_term_memory: Optional[Dict[str, Any]] = None,
    survey: Optional[Dict[str, str]] = None,
) -> str:
    plan = plan or {}
    print("[DEBUG] plan:", plan)

    tool = plan.get("tools", [None])[0] or plan.get("tool") or "general_chat"
    user_message = plan.get("original_user_message", "")
    args = plan.get("args") or {}

    print(f"🚀 [Tool Execution] Tool: {tool}")

    if tool == "trip_ideation":
        return run_trip_ideation_tool(user_message, context, survey=survey)
    elif tool == "itinerary_planner":
        return run_itinerary_planner_tool(user_message, context, weather_data, survey=survey)
    elif tool == "flight_search":
        return run_flight_search_tool(user_message, context, survey=survey)
    elif tool == "stay_search":
        return run_stay_search_tool(user_message, context, survey=survey)
    elif tool in ["accommodation_booking", "booking_action"]:
        return run_booking_action_tool(user_message, context)
    elif tool == "food_spot_search":
        return run_food_spot_search_tool(user_message, context, survey=survey)
    elif tool == "event_search":
        return run_event_search_tool(user_message, context)
    elif tool == "transportation_search":
        return transportation_search(args, context)
    elif tool == "transportation_batch":
        return transportation_batch(args, context)
    elif tool == "travel_warning_search":
        country = (args.get("country") or "").strip()
        if country:
            return render_travel_warning(country)
        return run_travel_warning_tool(user_message, context)
    elif tool == "local_guide":
        return run_local_guide_tool(user_message, context)
    elif tool == "budget_planner":
        return call_gemini(BUDGET_SYSTEM, f"컨텍스트: {context}\n질문: {user_message}")
    elif tool == "general_chat":
        return call_gemini(DEFAULT_AGENT_SYSTEM, f"컨텍스트:\n{context}\n\nUser: {user_message}")
    elif tool == "out_of_scope":
        return run_out_of_scope_tool(user_message, context)
    else:
        return call_gemini(DEFAULT_AGENT_SYSTEM, f"{context}\nUser: {user_message}")