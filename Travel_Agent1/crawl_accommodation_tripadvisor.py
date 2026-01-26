import requests
import json
import os
import sys
from dotenv import load_dotenv

sys.stdout.reconfigure(encoding='utf-8')
load_dotenv()

RAPIDAPI_KEY = "cffd4032abmsh7ad54f0b3e1fc9ep1d3278jsne0d76693fcaf"
RAPIDAPI_HOST = "travel-advisor.p.rapidapi.com"

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
        return None

# (2) 메인 검색 함수 (날짜 필수!)
def search_hotels_with_retry(location_name, check_in, check_out):
    
    # 1. ID 찾기
    location_id = get_location_id(location_name)
    if not location_id:
        return []

    print(f"[TripAdvisor] 숙소 검색 시작: {location_name}(ID:{location_id}) | {check_in} ~ {check_out}")

    url = f"https://{RAPIDAPI_HOST}/hotels/list"
    
    # 2. 정렬 옵션 바꿔가며 시도 (날짜가 포함된 가격을 찾기 위해)
    # recommended는 데이터가 없으면 0개를 줄 때가 많아 popularity를 먼저 씁니다.
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
                # 디버깅: 왜 0개인지 확인 (에러 메시지 등)
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
        
        # 가격 정보가 있는지 확인
        price_raw = hotel.get('price', '')
        # 날짜 검색이 성공했다면 가격이 있어야 정상이지만, 예약 마감이면 없을 수 있음
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
    print("\n🚀 817[테스트] / 2026-02-01 ~ 2026-02-03")
    res = search_hotels_with_retry("jeju-do", "2026-02-01", "2026-02-03")
    
    if res:
        print("\n" + "="*60)
        for i, item in enumerate(res[:5], 1):
            print(f"{i}. {item['name']}")
            print(f"   💰 {item['price']}")
            print(f"   ⭐ {item['rating']}")
            print("-" * 60)