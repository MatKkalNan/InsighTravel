# crawl_accommodation_tripadvisor.py
import requests
import json
import os
import sys
from dotenv import load_dotenv

sys.stdout.reconfigure(encoding='utf-8')

# .env 파일 로드
load_dotenv()

# ==================================================================
# [설정] 환경변수에서 API 키 가져오기
# ==================================================================
# Booking.com과 같은 RapidAPI 키를 공유해서 사용합니다.
RAPIDAPI_KEY = os.getenv("RAPIDAPI_KEY")
RAPIDAPI_HOST = "travel-advisor.p.rapidapi.com"

# 키가 없는 경우 에러 처리
if not RAPIDAPI_KEY:
    print("❌ [Error] .env 파일에서 RAPIDAPI_KEY를 찾을 수 없습니다.")
    print("   .env 파일을 확인하거나 'pip install python-dotenv'를 실행했는지 확인하세요.")
    sys.exit(1)

HEADERS = {
    "X-RapidAPI-Key": RAPIDAPI_KEY,
    "X-RapidAPI-Host": RAPIDAPI_HOST
}

# (1) 지역 ID 정밀 탐색 함수
def get_location_id(location_name: str):
    url = f"https://{RAPIDAPI_HOST}/locations/v2/auto-complete"
    params = {"query": location_name, "lang": "ko_KR", "units": "km"}
    
    print(f"[ID 검색] '{location_name}'에 대한 정확한 지역 ID를 찾습니다...")
    
    try:
        response = requests.get(url, headers=HEADERS, params=params)
        data = response.json()
        
        candidates = []
        
        if "data" in data and "Typeahead_autocomplete" in data["data"]:
            results = data["data"]["Typeahead_autocomplete"].get("results", [])
            
            for item in results:
                # detailsV2가 있는 항목만 유효함
                if "detailsV2" in item:
                    details = item["detailsV2"]
                    loc_id = details.get("locationId")
                    name = details.get("names", {}).get("name", "")
                    place_type = details.get("placeType", "UNKNOWN") # CITY, GEO 등 확인
                    
                    if loc_id:
                        candidates.append((loc_id, name, place_type))

        # 후보군 중에서 가장 적절한 것 선택
        if candidates:
            print(f"   -> 발견된 후보군: {candidates}")
            # 1순위: CITY 타입이면서 이름이 일치하는 것
            for cid, cname, ctype in candidates:
                if ctype == "CITY":
                    print(f"   ✅ 선택됨: {cname} (ID: {cid}, Type: CITY)")
                    return cid
            
            # 2순위: 그냥 첫 번째 결과 (GEO 등)
            first_id = candidates[0][0]
            print(f"   ⚠️ CITY 타입을 못 찾음. 첫 번째 후보 선택: {first_id}")
            return first_id

        print(f"❌ '{location_name}'에 대한 검색 결과가 없습니다.")
        return None

    except Exception as e:
        print(f"❌ ID 검색 중 에러: {e}")
        # 비상용 하드코딩 (최후의 수단)
        if "tokyo" in location_name.lower() or "도쿄" in location_name: return "298184"
        if "busan" in location_name.lower() or "부산" in location_name: return "297884"
        if "jeju" in location_name.lower() or "제주" in location_name: return "297390"
        return None

# (2) 메인 검색 함수 (날짜 필수!)
def search_hotels_with_retry(location_name, check_in, check_out):
    
    # 1. ID 찾기
    location_id = get_location_id(location_name)
    if not location_id:
        return []

    print(f"[TripAdvisor] 숙소 검색 시작: {location_name}(ID:{location_id}) | {check_in} ~ {check_out}")

    url = f"https://{RAPIDAPI_HOST}/hotels/list"
    
    # 2. 정렬 옵션 바꿔가며 시도
    sort_options = ["popularity", "price_low", "recommended"]
    
    for sort_opt in sort_options:
        print(f"   🔄 시도 중: 정렬 기준 = '{sort_opt}' ... ", end="")
        
        params = {
            "location_id": location_id,
            "checkin": check_in,
            "checkout": check_out,
            "adults": "2",
            "rooms": "1",
            "limit": "20",
            "currency": "KRW",
            "lang": "ko_KR",
            "sort": sort_opt 
        }

        try:
            response = requests.get(url, headers=HEADERS, params=params)
            data = response.json()
            hotels = data.get("data", [])
            
            if hotels:
                print(f"✅ 성공! ({len(hotels)}개 발견)")
                return parse_results(hotels)
            else:
                print("❌ 0개")
                # 디버깅: 왜 0개인지 확인
                if "errors" in data:
                    print(f"      (API 에러 메시지: {data['errors'][0]['message']})")

        except Exception as e:
            print(f"에러: {e}")
            continue

    print("🚨 [최종 실패] 해당 날짜/지역 조건으로 검색된 숙소가 없습니다. (API 데이터 부족 가능성)")
    return []

# (3) 결과 정리 함수
def parse_results(hotels):
    results = []
    for hotel in hotels:
        if "name" not in hotel: continue
        
        # 가격 정보 확인
        price_raw = hotel.get('price', '')
        price_text = str(price_raw) if price_raw else "예약 마감/문의 필요"

        item = {
            "source": "TripAdvisor",
            "name": str(hotel.get('name', '이름 없음')),
            "price": price_text, 
            "rating": str(hotel.get('rating', 'N/A')),
            "ranking": str(hotel.get('ranking', '')),
            "link": f"https://www.tripadvisor.co.kr/Search?q={hotel.get('name')}"
        }
        results.append(item)
    return results

# ==========================================
# 테스트 실행 (이 파일만 실행했을 때)
# ==========================================
if __name__ == "__main__":
    # 테스트: 제주도
    print("\n🚀 [테스트] 제주도 / 2026-02-01 ~ 2026-02-03")
    res = search_hotels_with_retry("jeju-do", "2026-02-01", "2026-02-03")
    
    if res:
        print("\n" + "="*60)
        for i, item in enumerate(res[:5], 1):
            print(f"{i}. {item['name']}")
            print(f"   💰 {item['price']}")
            print(f"   ⭐ {item['rating']}")
            print("-" * 60)