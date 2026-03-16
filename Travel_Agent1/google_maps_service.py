# google_maps_service.py
import os
import requests
from dotenv import load_dotenv
from typing import Optional, List, Dict

load_dotenv()


GOOGLE_MAPS_API_KEY = os.getenv("GOOGLE_MAPS_API_KEY")


def _maps_link_from_place_id(place_id: str) -> str:
    if not place_id:
        return ""
    return f"https://www.google.com/maps/place/?q=place_id:{place_id}"


def search_places_google(
    query: str,
    place_type: Optional[str] = None,
    max_results: int = 10,
    min_rating: float = 4.0,
    language: str = "ko",
) -> List[Dict]:
    """
    Google Places Text Search로 장소를 찾고,
    rating >= min_rating 인 것만 rating 높은 순으로 정렬해 반환.

    반환 예시:
    {
      "name": "가게명",
      "rating": 4.5,
      "user_ratings_total": 1200,
      "address": "주소",
      "place_id": "...",
      "link": "구글맵 링크",
      "types": ["restaurant", ...]
    }
    """
    if not GOOGLE_MAPS_API_KEY:
        print("[Google Maps] .env에 GOOGLE_MAPS_API_KEY가 없습니다.")
        return []

    if not query:
        return []

    url = "https://maps.googleapis.com/maps/api/place/textsearch/json"
    params = {
        "query": query,
        "key": GOOGLE_MAPS_API_KEY,
        "language": language,
    }
    if place_type:
        # textsearch는 type 파라미터 지원
        params["type"] = place_type

    try:
        resp = requests.get(url, params=params, timeout=15)
        data = resp.json()

        if data.get("status") not in ("OK", "ZERO_RESULTS"):
            print(f"[Google Maps] error status={data.get('status')} msg={data.get('error_message')}")
            return []

        results = []
        for item in data.get("results", []):
            # 영업 중인 곳 위주(정보가 없으면 그냥 통과)
            business_status = item.get("business_status")
            if business_status and business_status != "OPERATIONAL":
                continue

            rating = item.get("rating")
            if rating is None:
                continue
            try:
                rating_f = float(rating)
            except Exception:
                continue

            if rating_f < float(min_rating):
                continue

            place_id = item.get("place_id", "")
            results.append(
                {
                    "name": item.get("name", ""),
                    "rating": rating_f,
                    "user_ratings_total": int(item.get("user_ratings_total") or 0),
                    "address": item.get("formatted_address") or item.get("vicinity") or "",
                    "place_id": place_id,
                    "link": _maps_link_from_place_id(place_id),
                    "types": item.get("types") or [],
                }
            )

        # 평점 높은 순 -> 리뷰 수 많은 순
        results.sort(key=lambda x: (x["rating"], x["user_ratings_total"]), reverse=True)
        return results[:max_results]

    except Exception as e:
        print(f"[Google Maps] exception: {e}")
        return []

# -------------------------------------------------------------------
# [NEW] 교통/경로 정보 추출 함수 (Directions API)
# -------------------------------------------------------------------
def get_directions_info(origin: str, destination: str, mode: str = "transit") -> str:
    """
    출발지와 도착지 간의 교통 경로와 소요 시간을 반환합니다.
    mode: transit(대중교통), driving(자동차), walking(도보)
    """
    import re
    if not GOOGLE_MAPS_API_KEY:
        return "⚠️ 구글 맵스 API 키가 설정되지 않아 교통 정보를 불러올 수 없습니다."
        
    url = "https://maps.googleapis.com/maps/api/directions/json"
    params = {
        "origin": origin,
        "destination": destination,
        "mode": mode, 
        "language": "ko",
        "key": GOOGLE_MAPS_API_KEY
    }
    
    try:
        resp = requests.get(url, params=params, timeout=15)
        data = resp.json()
        
        if data.get("status") == "OK":
            route = data["routes"][0]["legs"][0]
            duration = route["duration"]["text"]
            distance = route["distance"]["text"]
            
            steps_info = []
            for step in route["steps"][:3]: # 응답이 너무 길어지지 않게 핵심 3단계만 추출
                travel_mode = step.get("travel_mode", "")
                if travel_mode == "TRANSIT":
                    transit = step.get("transit_details", {})
                    line = transit.get("line", {}).get("short_name") or transit.get("line", {}).get("name", "대중교통")
                    dep_stop = transit.get("departure_stop", {}).get("name", "")
                    arr_stop = transit.get("arrival_stop", {}).get("name", "")
                    steps_info.append(f"🚇 [{line}] {dep_stop} -> {arr_stop}")
                else:
                    # 도보 등 기타 수단 (정규식으로 HTML 태그 깔끔하게 제거)
                    instructions = re.sub(r'<[^>]+>', ' ', step.get("html_instructions", ""))
                    steps_info.append(f"🚶 {travel_mode} ({step['duration']['text']}) - {instructions.strip()}")
            
            step_str = " / ".join(steps_info)
            mode_ko = "대중교통" if mode == "transit" else ("자동차" if mode == "driving" else mode)
            return f"[{mode_ko}] ⏱ 총 소요시간: {duration} ({distance})\n📍 주요 경로: {step_str}"
            
        return f"해당 구간의 {mode} 경로를 찾을 수 없습니다. (상태: {data.get('status')})"
    except Exception as e:
        print(f"[Google Maps Directions] exception: {e}")
        return f"교통 정보 API 호출 중 오류 발생: {e}"
