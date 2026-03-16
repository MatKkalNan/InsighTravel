import os
import requests
from datetime import datetime, timedelta
from dotenv import load_dotenv

# 환경 변수 로드
load_dotenv()

# API 키 설정
SERPAPI_API_KEY = os.getenv("SERPAPI_API_KEY")
TOUR_API_KEY = os.getenv("TOUR_API_KEY")

# 지역 코드 매핑 상수
AREA_CODE_MAP = {
    "서울": "1", "인천": "2", "대전": "3", "대구": "4",
    "광주": "5", "부산": "6", "울산": "7", "세종": "8",
    "경기": "31", "강원": "32", "충북": "33", "충남": "34",
    "경북": "35", "경남": "36", "전북": "37", "전남": "38", "제주": "39"
}

# -------------------------------------------------------------------
# [Helper] 유틸리티 함수
# -------------------------------------------------------------------
def get_area_code(region: str) -> str:
    """지역명을 TourAPI 지역 코드로 변환"""
    if not region:
        return ""
    for key, val in AREA_CODE_MAP.items():
        if key in region:
            return val
    return ""

# -------------------------------------------------------------------
# 1. 해외/범용 이벤트 검색 (SerpAPI)
# -------------------------------------------------------------------
def search_events_serpapi(query: str) -> list:
    """SerpAPI Google Events를 사용하여 글로벌 이벤트 검색"""
    if not SERPAPI_API_KEY:
        print("⚠️ SERPAPI_API_KEY가 설정되지 않았습니다.")
        return []

    print(f"🔎 [SerpAPI] 이벤트 검색: '{query}'")
    
    url = "https://serpapi.com/search.json"
    params = {
        "engine": "google_events",
        "q": query,
        "hl": "ko",
        "gl": "kr",
        "api_key": SERPAPI_API_KEY
    }

    try:
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        events_results = data.get("events_results", [])
        return [{
            "type": "해외 이벤트",
            "title": ev.get("title", "제목 없음"),
            "date": ev.get("date", {}).get("when", "날짜 정보 없음"),
            "address": ", ".join(ev.get("address", [])) if ev.get("address") else "위치 정보 없음",
            "description": ev.get("description", "설명 없음"),
            "link": ev.get("link", "")
        } for ev in events_results]
            
    except Exception as e:
        print(f"⚠️ SerpAPI Error: {e}")
        return []

# -------------------------------------------------------------------
# 2. 국내 축제 및 문화시설 검색 (TourAPI 통합)
# -------------------------------------------------------------------
def search_korea_festivals_tourapi(region: str = "", start_date: str = "") -> list:
    """한국관광공사 API를 사용하여 국내 축제(Type 15) 및 문화시설(Type 14) 검색"""
    if not TOUR_API_KEY:
        print("⚠️ TOUR_API_KEY가 설정되지 않았습니다.")
        return []

    today_str = datetime.now().strftime("%Y%m%d")
    # 장기 축제 누락 방지를 위해 시작일 기준을 60일 전으로 설정
    api_start_str = (datetime.now() - timedelta(days=60)).strftime("%Y%m%d")
    area_code = get_area_code(region)
    
    combined_results = []
    base_url = "https://apis.data.go.kr/B551011/KorService2"

    # [A] 축제 정보 검색 (contentTypeId=15)
    try:
        festival_url = f"{base_url}/searchFestival2"
        params_f = {
            "serviceKey": TOUR_API_KEY,
            "numOfRows": "20",
            "pageNo": "1",
            "MobileOS": "ETC",
            "MobileApp": "TravelAgent",
            "_type": "json",
            "eventStartDate": api_start_str
        }
        if area_code: params_f["areaCode"] = area_code

        res_f = requests.get(festival_url, params=params_f, timeout=10)
        items_f = res_f.json().get("response", {}).get("body", {}).get("items", {}).get("item", [])
        
        if not isinstance(items_f, list):
            items_f = [items_f] if items_f else []
        
        for item in items_f:
            # 이미 종료된 행사는 필터링
            if item.get("eventenddate", "") < today_str:
                continue
            combined_results.append({
                "type": "축제/행사",
                "title": f"🎉 {item.get('title')}",
                "date": f"{item.get('eventstartdate')} ~ {item.get('eventenddate')}",
                "address": item.get("addr1", "위치 정보 없음"),
                "description": f"문의: {item.get('tel', '없음')}",
                "link": ""
            })
    except Exception as e:
        print(f"⚠️ TourAPI Festival Error: {e}")

    # [B] 문화시설 검색 (contentTypeId=14: 미술관, 박물관 등)
    try:
        culture_url = f"{base_url}/areaBasedList2"
        params_c = {
            "serviceKey": TOUR_API_KEY,
            "numOfRows": "15",
            "pageNo": "1",
            "MobileOS": "ETC",
            "MobileApp": "TravelAgent",
            "_type": "json",
            "listYN": "Y",
            "arrange": "A",
            "contentTypeId": "14"
        }
        if area_code: params_c["areaCode"] = area_code

        res_c = requests.get(culture_url, params=params_c, timeout=10)
        items_c = res_c.json().get("response", {}).get("body", {}).get("items", {}).get("item", [])
        
        if not isinstance(items_c, list):
            items_c = [items_c] if items_c else []
        
        for item in items_c:
            combined_results.append({
                "type": "문화/전시",
                "title": f"🏛️ {item.get('title')}",
                "date": "상시 운영",
                "address": item.get("addr1", "주소 없음"),
                "description": f"연락처: {item.get('tel', '없음')}",
                "link": ""
            })
    except Exception as e:
        print(f"⚠️ TourAPI Culture Error: {e}")

    return combined_results