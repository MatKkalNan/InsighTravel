#crawl_accommodation_amadeus.py

import os
import time
import json
import requests
import sys
from datetime import datetime, timedelta
from dotenv import load_dotenv
from deep_translator import GoogleTranslator

# 한글 출력 설정
sys.stdout.reconfigure(encoding='utf-8')

# .env 파일 로드
current_dir = os.path.dirname(os.path.abspath(__file__))
env_path = os.path.join(current_dir, '.env')
load_dotenv(env_path)

BASE_DIR = "data/accommodation_raw"
os.makedirs(BASE_DIR, exist_ok=True)

AMADEUS_CLIENT_ID = os.getenv("AMADEUS_API_KEY")
AMADEUS_CLIENT_SECRET = os.getenv("AMADEUS_API_SECRET")
AMADEUS_HOST = "api.amadeus.com" 

def get_amadeus_token():
    """ 1단계: 토큰 발급 """
    if not AMADEUS_CLIENT_ID or not AMADEUS_CLIENT_SECRET:
        print("❌ [오류] .env 파일 설정을 확인해주세요.")
        return None

    url = f"https://{AMADEUS_HOST}/v1/security/oauth2/token"
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    data = {
        "grant_type": "client_credentials",
        "client_id": AMADEUS_CLIENT_ID,
        "client_secret": AMADEUS_CLIENT_SECRET
    }
    
    try:
        response = requests.post(url, headers=headers, data=data)
        response.raise_for_status()
        return response.json().get("access_token")
    except Exception as e:
        print(f"❌ [토큰 발급 실패]: {e}")
        return None

def translate_to_english(text):
    """ 한글 -> 영어 번역 (필수) """
    if not text: return "Seoul"
    # 한글 포함 여부 체크
    is_korean = any(ord(char) > 127 for char in text)
    if is_korean:
        try:
            print(f"DEBUG: '{text}' 한글 감지 -> 영어로 번역 시도...", end="")
            translated = GoogleTranslator(source='auto', target='en').translate(text)
            print(f" 완료 ({translated})")
            return translated
        except:
            return text
    return text

def validate_dates(check_in, check_out):
    """ [NEW] 날짜 유효성 검사 및 자동 보정 """
    try:
        today = datetime.now().date()
        in_date = datetime.strptime(check_in, "%Y-%m-%d").date()
        out_date = datetime.strptime(check_out, "%Y-%m-%d").date()

        # 1. 과거 날짜인 경우 -> 내년으로 변경
        if in_date < today:
            print(f"⚠️ [경고] 입력된 날짜({in_date})가 과거입니다. 1년 뒤로 자동 조정합니다.")
            in_date = in_date.replace(year=today.year + 1)
            out_date = out_date.replace(year=today.year + 1)
        
        # 2. 체크아웃이 체크인보다 빠르거나 같을 때 -> 체크인 + 2일
        if out_date <= in_date:
             out_date = in_date + timedelta(days=2)

        return in_date.strftime("%Y-%m-%d"), out_date.strftime("%Y-%m-%d")
    except Exception as e:
        print(f"⚠️ 날짜 변환 중 오류({e}). 기본값(내일)으로 설정합니다.")
        tomorrow = datetime.now().date() + timedelta(days=1)
        after_tomorrow = tomorrow + timedelta(days=2)
        return tomorrow.strftime("%Y-%m-%d"), after_tomorrow.strftime("%Y-%m-%d")

def get_city_code(city_name, token):
    """ 2단계: 도시 코드 검색 """
    english_city_name = translate_to_english(city_name)
    url = f"https://{AMADEUS_HOST}/v1/reference-data/locations"
    headers = {"Authorization": f"Bearer {token}"}
    params = {"keyword": english_city_name, "subType": "CITY", "page[limit]": 1}
    
    print(f"DEBUG: [1단계] '{english_city_name}' 도시 코드 검색 중...", end="")
    try:
        response = requests.get(url, headers=headers, params=params)
        data = response.json()
        if "data" in data and len(data["data"]) > 0:
            code = data["data"][0]["iataCode"]
            print(f"✅ 성공! (Code: {code})")
            return code
        
        # 하드코딩 백업
        lower = english_city_name.lower()
        if "sapporo" in lower: return "SPK"
        if "osaka" in lower: return "OSA"
        if "fukuoka" in lower: return "FUK"
        if "tokyo" in lower: return "TYO"
        if "busan" in lower: return "PUS"
        if "seoul" in lower: return "SEL"
        return None
    except:
        return None

def get_hotel_ids(city_code, token):
    """ 2.5단계: 호텔 ID 리스트 가져오기 """
    url = f"https://{AMADEUS_HOST}/v1/reference-data/locations/hotels/by-city"
    headers = {"Authorization": f"Bearer {token}"}
    params = {
        "cityCode": city_code,
        "radius": 10,
        "radiusUnit": "KM",
        "hotelSource": "ALL"
    }
    
    print(f"DEBUG: [2단계] '{city_code}' 지역의 호텔 목록 조회 중...", end="")
    try:
        response = requests.get(url, headers=headers, params=params)
        data = response.json()
        hotels = data.get("data", [])
        
        if not hotels:
            print(f"❌ 호텔 없음")
            return []
            
        hotel_ids = [h["hotelId"] for h in hotels]
        print(f"✅ {len(hotel_ids)}개 호텔 발견!")
        return hotel_ids
    except:
        return []

def search_hotels_api(location, check_in, check_out, guests=2):
    """ 3단계: 최종 가격 검색 """
    token = get_amadeus_token()
    if not token: return []

    # 1. 날짜 자동 보정 (중요!)
    fixed_check_in, fixed_check_out = validate_dates(check_in, check_out)

    # 2. 도시 코드
    city_code = get_city_code(location, token)
    if not city_code: return []

    # 3. 호텔 ID 확보
    all_hotel_ids = get_hotel_ids(city_code, token)
    if not all_hotel_ids: return []

    # [최적화] 너무 많으면 20개만 (URL 길이 제한 방지)
    target_ids = all_hotel_ids[:20]
    ids_str = ",".join(target_ids)

    print(f"DEBUG: [3단계] 가격 검색 시작 ({fixed_check_in} ~ {fixed_check_out})...")
    
    url = f"https://{AMADEUS_HOST}/v3/shopping/hotel-offers"
    headers = {"Authorization": f"Bearer {token}"}
    
    params = {
        "hotelIds": ids_str,
        "adults": guests,
        "checkInDate": fixed_check_in,
        "checkOutDate": fixed_check_out,
        "roomQuantity": 1,
        "currency": "KRW",
        "bestRateOnly": "true",
        "lang": "KO"
    }

    try:
        response = requests.get(url, headers=headers, params=params)
        
        if response.status_code != 200:
            print(f"⚠️ API 호출 실패: {response.text}")
            return []

        data = response.json()
        offers = data.get("data", [])
        
        print(f"✅ [결과] 예약 가능한 호텔 {len(offers)}개를 찾았습니다!")

        results = []
        for offer in offers:
            try:
                hotel = offer.get("hotel", {})
                price = offer.get("offers", [])[0].get("price", {})
                
                name = hotel.get("name", "이름 없음").title()
                formatted_price = f"{price.get('currency', 'KRW')} {price.get('total', '0')}"
                rating = hotel.get("rating", "")

                results.append({
                    "source": "Amadeus",
                    "name": name,
                    "price": formatted_price,
                    "rating": f"{rating}성급" if rating else "정보 없음",
                    "link": f"https://www.google.com/search?q={name} hotel"
                })
            except:
                continue
        
        # 결과 파일 저장
        if results:
            filename = f"amadeus_{location}_{fixed_check_in}_{int(time.time())}.json"
            with open(os.path.join(BASE_DIR, filename), "w", encoding="utf-8") as f:
                json.dump(results, f, ensure_ascii=False, indent=2)
                
        return results

    except Exception as e:
        print(f"❌ [시스템 에러]: {e}")
        return []

if __name__ == "__main__":
    pass
    # 테스트
    # search_hotels_api("삿포로", "2024-02-10", "2024-02-12") # 일부러 과거 날짜로 테스트해도 작동함