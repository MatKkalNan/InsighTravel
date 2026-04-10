# tools.py
import os
import re
import json
from datetime import datetime
from typing import Dict, Any, List, Optional

from dotenv import load_dotenv
from openai import OpenAI

from date_parser import (
    resolve_date_expression,
    infer_checkout_or_return,
    sanitize_date_range,
    to_iso,
)

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
def run_trip_ideation_tool(user_message: str, context: str) -> str:
    user_prompt = build_ideation_user_prompt(context, user_message)
    return call_gemini(IDEATION_SYSTEM, user_prompt, temperature=0.7)


# -------------------------------------------------------------------
# 2. 일정 플래너 (OpenAI 추출 -> 지도 API -> Gemini 작성)
# -------------------------------------------------------------------
def run_itinerary_planner_tool(user_message: str, context: str, weather_data=None) -> str:
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
    user_prompt = build_itinerary_user_prompt(user_message, places_info, weather_info_text)
    return call_gemini(ITINERARY_SYSTEM, user_prompt, temperature=0.4)


# -------------------------------------------------------------------
# 3. 항공권 검색
# -------------------------------------------------------------------
def run_flight_search_tool(user_message: str, context: str) -> str:
    print("RUNNING: Flight Search")

    param_prompt = build_flight_param_prompt()
    params = extract_params_with_openai(param_prompt, user_message, context)

    origin = params.get("origin", "ICN")
    dest = params.get("destination")

    departure_text = params.get("departure_date_text", "")
    return_text = params.get("return_date_text", "")
    duration_text = params.get("duration_text", "")

    dep_date_obj = resolve_date_expression(departure_text)
    ret_date_obj = resolve_date_expression(return_text, base_date=dep_date_obj) if return_text else None

    if not ret_date_obj and duration_text:
        ret_date_obj = infer_checkout_or_return(dep_date_obj, duration_text)

    dep_date_obj, ret_date_obj = sanitize_date_range(dep_date_obj, ret_date_obj)

    dep_date = to_iso(dep_date_obj)
    ret_date = to_iso(ret_date_obj)

    if not dest or not dep_date:
        return "출발지, 목적지 또는 날짜 정보가 부족하여 항공권을 검색할 수 없습니다. 예: 다음주 금요일 도쿄 항공권 알려줘"

    print(f"✈️ API 호출 파라미터: {origin} -> {dest}, 날짜: {dep_date}, 귀국: {ret_date}")

    try:
        flight_data = search_flight_offers(origin, dest, dep_date, ret_date)
    except Exception as e:
        flight_data = f"항공권 검색 중 API 오류가 발생했습니다: {str(e)}"

    return summarize_flight_data(user_message, flight_data)


# -------------------------------------------------------------------
# 4. 숙소 검색
# -------------------------------------------------------------------
def run_stay_search_tool(user_message: str, context: str) -> str:
    print("RUNNING: Stay Search")

    params = extract_params_with_openai(STAY_PARAM_PROMPT, user_message, context)
    print("[DEBUG] extract_search_params 결과:", params)

    destination = params.get("destination")

    raw_guests = params.get("guests", 2)
    if isinstance(raw_guests, str):
        raw_guests = raw_guests.strip()
        if raw_guests in ["혼자", "1명", "한 명", "1"]:
            guests = 1
        elif raw_guests in ["둘", "2명", "두 명", "2", "미정"]:
            guests = 2
        else:
            try:
                guests = int(re.sub(r"[^\d]", "", raw_guests))
            except Exception:
                guests = 2
    else:
        try:
            guests = int(raw_guests)
        except (TypeError, ValueError):
            guests = 2

    check_in_text = params.get("check_in_text", "")
    check_out_text = params.get("check_out_text", "")
    duration_text = params.get("duration_text", "")

    check_in_obj = resolve_date_expression(check_in_text)
    check_out_obj = resolve_date_expression(check_out_text, base_date=check_in_obj) if check_out_text else None

    if not check_out_obj and duration_text:
        check_out_obj = infer_checkout_or_return(check_in_obj, duration_text)

    check_in_obj, check_out_obj = sanitize_date_range(check_in_obj, check_out_obj)

    check_in = to_iso(check_in_obj)
    check_out = to_iso(check_out_obj)

    print("[DEBUG] normalized stay params:", {
        "destination": destination,
        "check_in_text": check_in_text,
        "check_out_text": check_out_text,
        "duration_text": duration_text,
        "check_in": check_in,
        "check_out": check_out,
        "guests": guests,
    })

    if not destination:
        return "어느 지역의 숙소를 찾아드릴까요? 도시 이름을 말씀해 주세요."

    if not check_in:
        return "체크인 날짜 정보가 부족해요. 예: 내일부터 2박 3일 도쿄 숙소 찾아줘"

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

    user_msg = build_stay_user_prompt(user_message, raw_text)
    return call_gemini(STAY_SYSTEM, user_msg)


# -------------------------------------------------------------------
# 5. 맛집/명소 검색
# -------------------------------------------------------------------
def run_food_spot_search_tool(user_message: str, context: str) -> str:
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

    user_prompt = build_food_user_prompt(user_message, data_text)
    return call_gemini(FOOD_SYSTEM, user_prompt)

# -------------------------------------------------------------------
# 6. 축제/이벤트 검색
# -------------------------------------------------------------------
def run_event_search_tool(user_message: str, context: str) -> str:
    print("RUNNING: Unified Event/Festival/Culture Search (Domestic & International)")
    
    param_prompt = build_event_param_prompt(context)
    params = extract_params_with_openai(param_prompt, user_message, context)
    
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
        data_text = f"🔎 [{source_name} 검색 결과]\n"
        for idx, ev in enumerate(events[:10], 1):
            title = ev.get('title', '제목 없음')
            date = ev.get('date', '날짜 정보 없음')
            address = ev.get('address', '위치 정보 없음')
            description = ev.get('description', '')
            link = ev.get('link', '')
            etype = ev.get('type', '이벤트')

            data_text += f"{idx}. [{etype}] {title}\n"
            data_text += f"   📅 일정: {date}\n"
            data_text += f"   📍 위치: {address}\n"
            
            if description and description != "설명 없음":
                data_text += f"   💬 {description}\n"
            
            if link:
                data_text += f"   🔗 링크: {link}\n"
                
            data_text += "-" * 30 + "\n"
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
# 9. 여행 주의 경보
# -------------------------------------------------------------------
def run_travel_warning_tool(user_message: str, context: str) -> str:
    country = user_message.strip()
    return render_travel_warning(country)

# -------------------------------------------------------------------
# 10. 예약 실행 (에이전트 모드 트리거)
# -------------------------------------------------------------------
def run_booking_action_tool(user_message: str, context: str) -> str:
    print("RUNNING: Booking Action (Agent Mode)")

    param_prompt = build_booking_param_prompt()
    params = extract_params_with_openai(param_prompt, user_message, context)
    print(f"[DEBUG] booking params extracted: {params}")

    booking_type = params.get("booking_type", "hotel")
    
    if booking_type == "hotel":
        if any(w in user_message for w in ["비행기", "항공", "편도", "왕복", "출국", "귀국"]):
            booking_type = "flight"

    destination    = params.get("destination", "")
    destination_kr = params.get("destination_kr", destination)
    guests         = int(params.get("guests") or 2)
    session_id     = "default"

    raw_index      = params.get("item_index")
    already_chosen = raw_index is not None
    item_index     = int(raw_index) if already_chosen else 0

    current_year = datetime.now().year

    if booking_type == "hotel":
        check_in  = params.get("check_in")  or f"{current_year}-04-01"
        check_out = params.get("check_out") or f"{current_year}-04-04"

        all_hotels = []
        try:
            from crawl_accommodation_booking_com import search_hotels_api as search_booking
            bk = search_booking(destination, check_in, check_out, guests)
            if bk:
                for h in bk: h['source'] = 'Booking.com'
                all_hotels.extend(bk)
        except Exception as e:
            print(f"Booking.com Error: {e}")

        try:
            from crawl_accommodation_amadeus import search_hotels_api as search_amadeus
            am = search_amadeus(destination, check_in, check_out, guests)
            if am:
                for h in am: h['source'] = 'Amadeus'
                all_hotels.extend(am)
        except Exception as e:
            print(f"Amadeus Error: {e}")

        if not all_hotels:
            return "예약할 수 있는 호텔을 찾지 못했습니다. 목적지와 날짜를 다시 확인해주세요."

        booking_store.save_temp_data(session_id, "hotel", all_hotels[:10])

        if already_chosen:
            chosen_name = (all_hotels[item_index].get("name") or "") if item_index < len(all_hotels) else ""
            bot_message = f"✅ {chosen_name or destination_kr + ' 호텔'} 예약을 진행할게요!"
        else:
            bot_message = f"🔍 {destination_kr} 숙소 검색이 완료됐어요! 예약할 숙소를 선택해 주세요."

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
        origin   = params.get("origin", "ICN")
        dep_date = params.get("departure_date") or params.get("check_in") or f"{current_year}-04-01"
        ret_date = params.get("return_date") or params.get("check_out") or None

        is_roundtrip_booking = bool(ret_date)
        trip_type_label = f"왕복 ({dep_date} → {ret_date})" if is_roundtrip_booking else f"편도 ({dep_date})"
        print(f"✈️  [항공권 예약 타입] 🔁 {trip_type_label}" if is_roundtrip_booking else f"✈️  [항공권 예약 타입] ➡  {trip_type_label}")
        print(f"✈️  [구간] {origin} → {destination} ({destination_kr}), 인원: {guests}명")

        try:
            flight_raw = search_flight_offers(origin, destination, dep_date, ret_date)
        except Exception as e:
            flight_raw = f"항공편 검색 오류: {e}"

        flight_items = _parse_flight_items_for_booking(
            origin, destination, destination_kr, dep_date, ret_date, flight_raw
        )
        booking_store.save_temp_data(session_id, "flight", flight_items)

        if already_chosen:
            chosen_airline = (flight_items[item_index].get("airline") or "") if item_index < len(flight_items) else ""
            bot_message = f"✅ {chosen_airline or destination_kr + ' 항공편'} 예약을 진행할게요!"
        else:
            bot_message = f"🔍 {destination_kr} 항공권 검색이 완료됐어요! 예약할 항공편을 선택해 주세요."

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


def _parse_flight_items_for_booking(
    origin: str, destination: str, destination_kr: str,
    dep_date: str, ret_date: Optional[str], raw_text: str
) -> List[Dict[str, Any]]:
    """
    flight_service.search_flight_offers()의 텍스트 결과를 파싱하여
    booking 페이지에서 쓸 수 있는 구조화된 리스트로 변환.
    파싱 실패 시 최소 1개의 fallback 항목을 반환.
    """
    items: List[Dict[str, Any]] = []

    def _extract_airline_from_line(line: str) -> str:
        bracket = re.search(r"\[([^\]]+)\]", line)
        if bracket:
            raw = bracket.group(1).strip()
            fn_match = re.search(r"\(([A-Z0-9]{2,7})\)", raw)
            airline_name = re.sub(r"\s*\([A-Z0-9]{2,7}\)", "", raw).strip()
            return airline_name, fn_match.group(1) if fn_match else ""
        parts = line.strip().lstrip("🛫🛬 ").split()
        if parts:
            return parts[0], ""
        return "", ""

    def _extract_times(line: str):
        times = re.findall(r'(?:(?:\d{4}-)?\d{1,2}-\d{1,2}\s+)?\d{1,2}:\d{2}(?:\s*[APap][Mm])?', line)
        if len(times) >= 2:
            return times[0].strip(), times[1].strip()
        return "", ""

    if isinstance(raw_text, str):
        blocks = [b.strip() for b in raw_text.split("\n\n") if "🎫" in b]
        for block in blocks[:10]:
            lines = block.splitlines()
            header = lines[0] if lines else ""

            is_roundtrip = "(왕복)" in header

            cabin = "일반석"
            for c in ["일등석", "비즈니스", "프리미엄 일반석", "일반석"]:
                if c in block:
                    cabin = c
                    break

            out_line = ""
            ret_line = ""
            for line in lines[1:]:
                if "🛫" in line:
                    out_line = line
                elif "🛬" in line:
                    ret_line = line

            target_line = out_line if out_line else (lines[1] if len(lines) > 1 else "")
            airline, flight_number = _extract_airline_from_line(target_line)

            dep_time, dep_arr_time = _extract_times(out_line)
            ret_dep_time, ret_arr_time = _extract_times(ret_line) if ret_line else ("", "")

            duration = ""
            dur_match = re.search(r"(\d+시간\s*\d*분?|\d+분)", out_line or block)
            if dur_match:
                duration = dur_match.group(1)

            ret_duration = ""
            if ret_line:
                rdur_match = re.search(r"(\d+시간\s*\d*분?|\d+분)", ret_line)
                if rdur_match:
                    ret_duration = rdur_match.group(1)

            stops = "직항"
            if "경유" in (out_line or block):
                stops_match = re.search(r"(\d+회 경유)", out_line or block)
                stops = stops_match.group(1) if stops_match else "경유"

            baggage = ""
            bag_match = re.search(r"🧳([\d]+[개kg]+)", block)
            if bag_match:
                baggage = bag_match.group(0)

            price_str = ""
            price_match = re.search(r"💰\s*([\d,]+원|가격정보없음)", block)
            if price_match:
                price_str = price_match.group(1)

            items.append({
                "airline": airline or "항공사 정보 없음",
                "flight_number": flight_number,
                "origin": origin,
                "destination": destination,
                "destination_kr": destination_kr,
                "is_roundtrip": is_roundtrip,
                "dep_time": dep_time or dep_date,
                "dep_arr_time": dep_arr_time or "",
                "ret_dep_time": ret_dep_time,
                "ret_arr_time": ret_arr_time,
                "dep_date": dep_date,
                "ret_date": ret_date or "",
                "duration": duration or "-",
                "ret_duration": ret_duration or "-",
                "stops": stops,
                "cabin": cabin,
                "baggage": baggage,
                "price": price_str or "가격 정보 없음",
                "raw_text": block,
            })

    if not items:
        items.append({
            "airline": "검색된 항공편",
            "flight_number": "",
            "origin": origin,
            "destination": destination,
            "destination_kr": destination_kr,
            "is_roundtrip": bool(ret_date),
            "dep_time": dep_date,
            "dep_arr_time": "",
            "ret_dep_time": ret_date or "",
            "ret_arr_time": "",
            "dep_date": dep_date,
            "ret_date": ret_date or "",
            "duration": "-",
            "ret_duration": "-",
            "stops": "-",
            "cabin": "일반석",
            "baggage": "",
            "price": "가격 정보 없음",
            "raw_text": raw_text if isinstance(raw_text, str) else "",
        })

    return items


# -------------------------------------------------------------------
# 메인 라우터
# -------------------------------------------------------------------
def run_tools_from_plan(
    plan: Dict[str, Any],
    context: str,
    weather_date: Optional[dict] = None,
    long_term_memory: Optional[Dict[str, Any]] = None,
) -> str:
    plan = plan or {}
    tool = plan.get("tools", ["general_chat"])[0]
    user_message = plan.get("original_user_message", "")

    args = plan.get("args") or {}

    print(f"🚀 [Tool Execution] Tool: {tool}")

    if tool == "trip_ideation":
        return run_trip_ideation_tool(user_message, context)
    elif tool == "itinerary_planner":
        return run_itinerary_planner_tool(user_message, context, plan.get("weather_data"))
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
    
    elif tool == "travel_warning_search":
        args = plan.get("args", {}) or {}
        country = (args.get("country") or "").strip()
        if country:
            return render_travel_warning(country)
        return run_travel_warning_tool(user_message, context)
    elif tool == "local_guide":
        return run_local_guide_tool(user_message, context)
    elif tool == "booking_action":
        return run_booking_action_tool(user_message, context)
    elif tool == "budget_planner":
        return call_gemini(BUDGET_SYSTEM, f"컨텍스트: {context}\n질문: {user_message}")
    elif tool == "out_of_scope":
        return "여행과 관련된 질문을 해주시면 기쁘게 도와드릴 수 있습니다! 😊"
    else:
        return call_gemini(DEFAULT_AGENT_SYSTEM, f"{context}\nUser: {user_message}")