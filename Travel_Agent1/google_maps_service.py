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
