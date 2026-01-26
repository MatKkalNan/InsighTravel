import os
import google.generativeai as genai
from dotenv import load_dotenv

# [변경] 프롬프트 모듈 임포트
from prompts.gemini_prompts import GEMINI_CORE_SYSTEM, get_flight_summary_prompt

load_dotenv()

GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")

# 1. 모델 설정 (Gemini 2.5 Flash 고정 - 기존 유지)
if GOOGLE_API_KEY:
    genai.configure(api_key=GOOGLE_API_KEY)
    
    # 사용자가 요청한 'gemini-2.5-flash' 모델로 설정
    try:
        default_model = genai.GenerativeModel("gemini-2.5-flash")
        print("✅ Gemini 2.5 Flash 모델이 설정되었습니다.")
    except Exception as e:
        print(f"⚠️ 모델 설정 중 오류 발생: {e}")
        default_model = None
else:
    default_model = None
    print("⚠️ GOOGLE_API_KEY가 없습니다. Gemini 기능이 제한됩니다.")

def call_gemini(system_role: str, user_data_prompt: str, temperature: float = 0.4) -> str:
    """
    OpenAI 스타일의 입력을 받아 Gemini로 처리하는 범용 함수
    """
    if not default_model:
        return "Gemini API Key가 설정되지 않았거나 모델을 불러올 수 없습니다."

    try:
        # [변경] GEMINI_CORE_SYSTEM(기본 페르소나) + system_role(현재 역할) + user_data_prompt(데이터) 결합
        combined_prompt = f"{GEMINI_CORE_SYSTEM}\n\n[Current Role]\n{system_role}\n\n[Data & Request]\n{user_data_prompt}"
        
        config = genai.GenerationConfig(temperature=temperature)
        response = default_model.generate_content(combined_prompt, generation_config=config)
        
        return response.text.strip()
    except Exception as e:
        return f"❌ Gemini 호출 중 오류 발생: {e}"

def summarize_flight_data(user_query, flight_raw_data):
    """
    항공권 데이터 전용 요약 함수
    """
    if not flight_raw_data or "찾을 수 없습니다" in flight_raw_data:
        return flight_raw_data

    # [변경] 하드코딩 제거 -> 프롬프트 모듈 사용
    user_prompt = get_flight_summary_prompt(user_query, flight_raw_data)
    
    # "항공권 컨설턴트"라는 역할만 부여 (구체적 지시는 프롬프트 파일에 있음)
    return call_gemini("당신은 '항공권 전문 분석가'입니다.", user_prompt, temperature=0.3)