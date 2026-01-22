# crawl_accommodation_booking_com.py
import os
import time
import json
import requests
import sys

sys.stdout.reconfigure(encoding='utf-8')

BASE_DIR = "data/accommodation_raw"
os.makedirs(BASE_DIR, exist_ok=True)

# API 키와 호스트
RAPIDAPI_KEY = "cffd4032abmsh7ad54f0b3e1fc9ep1d3278jsne0d76693fcaf"
RAPIDAPI_HOST = "booking-com.p.rapidapi.com"

HEADERS = {
    "X-RapidAPI-Key": RAPIDAPI_KEY,
    "X-RapidAPI-Host": RAPIDAPI_HOST
}

def get_destination_id(location_name: str):
    # 1. v1/hotels/locations (영어 검색 권장) 시도
    url = f"https://{RAPIDAPI_HOST}/v1/hotels/locations"
    params = {"name": location_name, "locale": "en-gb"}
    
    print(f"DEBUG: [1단계] 지역 '{location_name}' ID 검색 중... ", end="")
    
    try:
        response = requests.get(url, headers=HEADERS, params=params)
        data = response.json()
        
        if isinstance(data, list) and len(data) > 0:
            dest_id = data[0].get("dest_id")
            print(f"✅ 성공! (ID: {dest_id})")
            return dest_id, data[0].get("dest_type")
        else:
            print(f"❌ 실패. (결과 없음)")
            
            # 2. 실패 시 auto-complete (한글/영어 혼용) 시도 (백업)
            print(f"DEBUG: [2단계] 백업 검색(auto-complete) 시도... ", end="")
            url2 = f"https://{RAPIDAPI_HOST}/locations/auto-complete"
            params2 = {"text": location_name, "languagecode": "en-us"}
            
            resp2 = requests.get(url2, headers=HEADERS, params=params2)
            data2 = resp2.json()
            
            if isinstance(data2, list) and len(data2) > 0:
                dest_id = data2[0].get("dest_id")
                print(f"✅ 성공! (ID: {dest_id})")
                return dest_id, data2[0].get("dest_type")
            else:
                print("❌ 완전히 실패.")
                return None, None

    except Exception as e:
        print(f"\n❌ [Error] 지역 검색 중 에러: {e}")
        return None, None

def search_hotels_api(location, check_in, check_out, guests=2):
    dest_id, dest_type = get_destination_id(location)
    if not dest_id:
        print(f"❌ [결과] 지역 ID를 찾지 못해 종료합니다.")
        return []

    print(f"DEBUG: [3단계] 숙소 검색 시작 ({check_in} ~ {check_out})...")

    url = f"https://{RAPIDAPI_HOST}/v1/hotels/search"
    
    params = {
        "dest_id": dest_id,
        "dest_type": dest_type,
        "checkin_date": check_in,
        "checkout_date": check_out,
        "adults_number": guests,
        "room_number": "1",
        "locale": "ko",
        "filter_by_currency": "KRW",
        "order_by": "popularity",
        "units": "metric"
    }
    
    try:
        response = requests.get(url, headers=HEADERS, params=params)
        data = response.json()
        hotels = data.get('result', [])
        
        if not hotels:
            print(f"❌ [결과] 숙소 리스트가 0개입니다. (날짜가 너무 멀거나 예약 불가)")
        else:
            print(f"✅ [결과] {len(hotels)}개의 숙소를 찾았습니다!")

        results = []
        for hotel in hotels[:10]: 
            try:
                price_text = "가격정보 없음"
                if 'composite_price_breakdown' in hotel:
                    gross = hotel['composite_price_breakdown'].get('gross_amount', {})
                    if 'value' in gross:
                        price_text = f"{int(gross['value']):,}원"

                item = {
                    "name": hotel.get('hotel_name'),
                    "price": price_text,
                    "rating": hotel.get('review_score', 'N/A'),
                    "address": hotel.get('address'),
                    "link": hotel.get('url'),
                }
                results.append(item)
            except:
                continue
        
        return results

    except Exception as e:
        print(f"❌ [Error] 숙소 검색 중 에러: {e}")
        return []
