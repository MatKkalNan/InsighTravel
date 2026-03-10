# event_service.py
import os
import requests
from dotenv import load_dotenv

load_dotenv()

SERPAPI_API_KEY = os.getenv("SERPAPI_API_KEY")

def search_events_serpapi(query: str) -> list:
    """
    SerpAPI의 Google Events 엔진을 사용하여 축제/이벤트를 검색합니다.
    """
    if not SERPAPI_API_KEY:
        print("⚠️ SERPAPI_API_KEY is not set.")
        return []

    print(f"🔎 SerpAPI Event Search for: '{query}'")
    
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
        structured_events = []
        
        for event in events_results:
            title = event.get("title", "제목 없음")
            date = event.get("date", {}).get("when", "날짜 정보 없음")
            address = ", ".join(event.get("address", [])) if event.get("address") else "위치 정보 없음"
            description = event.get("description", "설명 없음")
            link = event.get("link", "")
            
            structured_events.append({
                "title": title,
                "date": date,
                "address": address,
                "description": description,
                "link": link
            })
            
        return structured_events
        
    except requests.exceptions.RequestException as e:
        print(f"⚠️ SerpAPI Request Error: {e}")
        return []
    except Exception as e:
        print(f"⚠️ SerpAPI Parsing Error: {e}")
        return []
