# gemini_service.py
import os
import google.generativeai as genai
from dotenv import load_dotenv

# 👉 프롬프트 임포트
from prompts import FLIGHT_SUMMARY_SYSTEM, build_flight_summary_user_prompt

load_dotenv()
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")

# 1. 모델 설정 (Gemini 2.5 Flash 고정)
if GOOGLE_API_KEY:
    genai.configure(api_key=GOOGLE_API_KEY)
    
    try:
        default_model = genai.GenerativeModel("gemini-2.5-flash")
        print("✅ Gemini 2.5 Flash 모델이 설정되었습니다.")
    except Exception as e:
        print(f"⚠️ 모델 설정 중 오류 발생: {e}")
        default_model = None
else:
    default_model = None
    print("⚠️ GOOGLE_API_KEY가 없습니다. Gemini 기능이 제한됩니다.")

def call_gemini(system_prompt: str, user_prompt: str, temperature: float = 0.4) -> str:
    """
    OpenAI 스타일의 입력을 받아 Gemini로 처리하는 범용 함수
    """
    if not default_model:
        return "Gemini API Key가 설정되지 않았거나 모델을 불러올 수 없습니다."

    try:
        combined_prompt = f"{system_prompt}\n\n[User Context/Message]\n{user_prompt}"
        
        config = genai.GenerationConfig(temperature=temperature)
        response = default_model.generate_content(combined_prompt, generation_config=config)
        
        return response.text.strip()
    except Exception as e:
        return f"❌ Gemini 호출 중 오류 발생: {e}"

def summarize_flight_data(user_query, flight_raw_data, survey: dict = None):
    """
    항공권 데이터 전용 요약 함수
    """
    if not flight_raw_data or "찾을 수 없습니다" in flight_raw_data:
        return flight_raw_data

    # 👉 프롬프트 중앙화 적용
    user_prompt = build_flight_summary_user_prompt(user_query, flight_raw_data, survey=survey)
    
    return call_gemini(FLIGHT_SUMMARY_SYSTEM, user_prompt, temperature=0.3)