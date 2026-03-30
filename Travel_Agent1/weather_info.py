import os
import requests
from datetime import datetime, timedelta

def get_insight_weather_data(lat, lon, travel_date_str):
    """
    lat, lon: 위도, 경도
    travel_date_str: 'YYYY-MM-DD' 형식의 여행 날짜
    """
    # API 키 
    OWM_API_KEY = os.getenv("OWM_API_KEY")
    VC_API_KEY = os.getenv("VC_API_KEY")
    
    # 날짜 계산 (오늘로부터 며칠 뒤인지 확인)
    travel_date = datetime.strptime(travel_date_str, '%Y-%m-%d')
    days_diff = (travel_date - datetime.now()).days

    # 1. Visual Crossing 호출 (통계 및 장기 예보용)
    # Timeline API는 특정 날짜를 지정하여 과거/미래 데이터를 가져오기 용이
    vc_url = f"https://weather.visualcrossing.com/VisualCrossingWebServices/rest/services/timeline/{lat},{lon}/{travel_date_str}"
    vc_params = {
        'unitGroup': 'metric',  # 섭씨 온도 사용
        'key': VC_API_KEY,
        'contentType': 'json'
    }
    
    try:
        vc_response = requests.get(vc_url, params=vc_params)
        vc_data = vc_response.json()
        # VC 데이터에서 기온, 강수확률 등 추출
        vc_temp = vc_data['days'][0].get('temp')
        vc_precip_prob = vc_data['days'][0].get('precipprob')
    except Exception as e:
        print(f"Visual Crossing 호출 오류: {e}")
        vc_data = None

    # 2. OpenWeatherMap 호출 (단기 실시간 예보용 - 8일 이내일 때만 유효)
    owm_data = None
    if 0 <= days_diff <= 7:
        owm_url = "https://api.openweathermap.org/data/3.0/onecall"
        owm_params = {
            'lat': lat,
            'lon': lon,
            'exclude': 'minutely,hourly', # 필요한 데이터만 선택
            'appid': OWM_API_KEY,
            'units': 'metric'
        }
        try:
            owm_response = requests.get(owm_url, params=owm_params)
            owm_data = owm_response.json()
            # 여행 날짜에 해당하는 index 찾아서 데이터 추출 (daily 리스트 활용)
            # owm_temp = owm_data['daily'][days_diff]['temp']['day']
        except Exception as e:
            print(f"OpenWeatherMap 호출 오류: {e}")

    return {
        "historical_stats": vc_data,
        "realtime_forecast": owm_data,
        "is_reliable": days_diff <= 7  # 7일 이내면 실시간 예보 포함이라 더 신뢰도 높음
    }