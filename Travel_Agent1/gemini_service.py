import os
import google.generativeai as genai
from dotenv import load_dotenv

load_dotenv()

GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")

# 1. 모델 설정 (Gemini 2.5 Flash 고정)
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

def call_gemini(system_prompt: str, user_prompt: str, temperature: float = 0.4) -> str:
    """
    OpenAI 스타일의 입력을 받아 Gemini로 처리하는 범용 함수
    """
    if not default_model:
        return "Gemini API Key가 설정되지 않았거나 모델을 불러올 수 없습니다."

    try:
        # Gemini는 System Prompt를 별도 파라미터로 받거나 프롬프트 앞단에 붙입니다.
        combined_prompt = f"{system_prompt}\n\n[User Context/Message]\n{user_prompt}"
        
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

    system_prompt = "당신은 유능한 여행 항공권 컨설턴트입니다."
    user_prompt = f"""
    아래 항공권 데이터를 분석해서 사용자 질문에 맞춰 가장 추천할 만한 옵션 3가지를 꼽아주고 이유를 설명해 줘.
    
    [사용자 질문]
    {user_query}

    [항공권 데이터]
    {flight_raw_data}

    [규칙]
    1. 가격, 시간, 경유 여부를 종합해 '최고의 가성비', '최단 시간' 등의 타이틀을 붙여줘.
    2. 데이터에 있는 예매 링크(URL)는 절대 변형하지 말고 그대로 출력해.
    3. 말투는 정중하고 친절하게.
    """
    
    return call_gemini(system_prompt, user_prompt, temperature=0.3)