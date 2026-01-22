# naver_service.py
import os
import urllib.parse
import requests
from dotenv import load_dotenv

load_dotenv()

NAVER_CLIENT_ID = os.getenv("NAVER_CLIENT_ID")
NAVER_CLIENT_SECRET = os.getenv("NAVER_CLIENT_SECRET")

def search_places_naver(query: str, display: int = 5, sort: str = "comment"):
    """
    네이버 지역 검색 API
    :param query: 검색어 (예: '강남역 맛집', '경주 가볼만한곳')
    :param display: 가져올 결과 개수
    :param sort: 'random'(정확도순) 또는 'comment'(리뷰많은순)
    """
    if not NAVER_CLIENT_ID or not NAVER_CLIENT_SECRET:
        print("❌ [Naver] .env 파일에 NAVER_CLIENT_ID 또는 SECRET이 없습니다.")
        return []

    print(f"🔎 [Naver API] '{query}' 검색 중... (정렬: {sort})")

    enc_query = urllib.parse.quote(query)
    url = f"https://openapi.naver.com/v1/search/local.json?query={enc_query}&display={display}&start=1&sort={sort}"
    
    headers = {
        "X-Naver-Client-Id": NAVER_CLIENT_ID,
        "X-Naver-Client-Secret": NAVER_CLIENT_SECRET
    }

    try:
        response = requests.get(url, headers=headers)
        if response.status_code != 200:
            print(f"❌ [Naver Error] {response.status_code} : {response.text}")
            return []

        data = response.json()
        items = data.get("items", [])
        
        results = []
        for item in items:
            # HTML 태그 제거 (<b>맛집</b> 등)
            clean_title = item['title'].replace("<b>", "").replace("</b>", "")
            results.append({
                "title": clean_title,
                "category": item.get('category', '기타'),
                "address": item.get('roadAddress') or item.get('address'),
                "link": item.get('link'),
                "mapx": item.get('mapx'),
                "mapy": item.get('mapy')
            })
            
        print(f"✅ [Naver] {len(results)}건 확보 완료.")
        return results

    except Exception as e:
        print(f"❌ [Naver Exception] {e}")
        return []