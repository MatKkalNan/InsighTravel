# flight_service.py
# ---------------------------------------------------------
# Amadeus + Google Flights 하이브리드 검색 모듈 (Top 5 통합 버전)
# ---------------------------------------------------------
from __future__ import annotations

import os
import re
import requests
import statistics
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from dotenv import load_dotenv

try:
    from amadeus import Client as AmadeusClient
except Exception:
    AmadeusClient = None

load_dotenv()

SERPAPI_KEY = os.getenv("SERPAPI_API_KEY")
SERPAPI_ENDPOINT = "https://serpapi.com/search"

# ---------------------------------------------------------
# 1) Amadeus client setup
# ---------------------------------------------------------
_amadeus: Optional[Any] = None
if AmadeusClient:
    try:
        _amadeus = AmadeusClient(
            client_id=os.getenv("AMADEUS_API_KEY"),
            client_secret=os.getenv("AMADEUS_API_SECRET"),
            hostname=os.getenv("AMADEUS_HOSTNAME", "production"),
        )
    except Exception as e:
        print(f"⚠️ Amadeus Client 설정 오류: {e}")
        _amadeus = None

AIRLINE_MAP = {
    "KE": "대한항공", "OZ": "아시아나", "7C": "제주항공",
    "LJ": "진에어", "TW": "티웨이", "RS": "에어서울",
    "BX": "에어부산", "ZE": "이스타", "JL": "일본항공",
    "NH": "ANA", "DL": "델타항공", "UA": "유나이티드",
    "VN": "베트남항공", "SQ": "싱가포르항공", "CX": "캐세이퍼시픽",
    "AF": "에어프랑스", "EK": "에미레이트", "TK": "터키항공", "LH": "루프트한자",
    "AA": "아메리칸항공", "AC": "에어캐나다", "CA": "중국국제항공", "MU": "동방항공",
    "FM": "상하이항공", "CZ": "중국남방항공",
}

CABIN_MAP_AMADEUS = {
    "ECONOMY": "일반석", "PREMIUM_ECONOMY": "프리미엄 일반석",
    "BUSINESS": "비즈니스", "FIRST": "일등석",
}

CABIN_TO_GOOGLE_TRAVEL_CLASS = {
    "ECONOMY": 1, "PREMIUM_ECONOMY": 2, "BUSINESS": 3, "FIRST": 4,
}

# ---------------------------------------------------------
# 2) Shared helpers
# ---------------------------------------------------------
def _fmt_price(p: int) -> str:
    return "가격정보없음" if not p or p <= 0 else f"{p:,}원"

def _safe_json(resp: requests.Response) -> Dict[str, Any]:
    try:
        return resp.json()
    except Exception:
        return {"error": f"Non-JSON response (status={resp.status_code})", "raw": resp.text[:1000]}

def _clean_iata_list(val: Any) -> List[str]:
    if not val: return []
    if isinstance(val, list): raw = val
    elif isinstance(val, str): raw = re.split(r"[,/ ]+", val.strip())
    else: return []
    out = []
    for x in raw:
        x = (x or "").strip().upper()
        if re.fullmatch(r"[A-Z0-9]{2}", x): out.append(x)
    return list(dict.fromkeys(out))

def parse_google_price(flight: Dict[str, Any]) -> int:
    candidates = []
    candidates += [flight.get("price"), flight.get("total_price"), flight.get("price_raw")]
    if isinstance(flight.get("price"), dict):
        candidates += [flight["price"].get("amount"), flight["price"].get("raw")]
    
    booking = flight.get("booking_options") or []
    if isinstance(booking, list):
        for b in booking[:3]:
            candidates.append(b.get("price"))

    for c in candidates:
        if isinstance(c, (int, float)) and c > 0: return int(c)
        if isinstance(c, str):
            nums = re.sub(r"[^\d]", "", c)
            if nums and int(nums) > 0: return int(nums)
    return 0

def _sum_duration_minutes(legs: List[Dict[str, Any]]) -> Optional[int]:
    total = 0
    seen = False
    for leg in legs:
        d = leg.get("duration")
        if isinstance(d, (int, float)) and d > 0:
            total += int(d)
            seen = True
    return total if seen else None

def _leg_time(leg: Dict[str, Any], which: str) -> str:
    ap = leg.get(which) or {}
    return ap.get("time", "") if isinstance(ap, dict) else ""

def _leg_airport_id(leg: Dict[str, Any], which: str) -> str:
    ap = leg.get(which) or {}
    return (ap.get("id") or ap.get("code") or "").strip().upper() if isinstance(ap, dict) else ""

def _route_matches_google(legs: List[Dict[str, Any]], origin: str, dest: str) -> bool:
    if not legs: return False
    o, d = _leg_airport_id(legs[0], "departure_airport"), _leg_airport_id(legs[-1], "arrival_airport")
    if not o or not d: return True
    return (o == origin) and (d == dest)

@dataclass
class RenderedFlight:
    source: str
    price: int
    text: str
    key: str

# ---------------------------------------------------------
# 3) Amadeus logic
# ---------------------------------------------------------
def _format_duration_amadeus(pt: Optional[str]) -> str:
    if not pt: return ""
    return pt.replace("PT", "").replace("H", "시간 ").replace("M", "분").strip()

def _amadeus_flight_info(itinerary: Dict[str, Any]) -> str:
    segs = itinerary.get("segments", [])
    if not segs: return "(정보없음)"
    dur = _format_duration_amadeus(itinerary.get("duration"))
    first, last = segs[0], segs[-1]
    
    cc = first.get("carrierCode", "")
    cname = AIRLINE_MAP.get(cc, cc)
    fn = first.get("number", "")
    flight_no = f"{cc}{fn}" if fn else ""  # 예: KE701
    
    dep = (first.get("departure") or {}).get("at", "")[5:16].replace("T", " ")
    arr = (last.get("arrival") or {}).get("at", "")[5:16].replace("T", " ")
    
    stops = len(segs) - 1
    rtype = "직항" if stops == 0 else f"{stops}회 경유"
    flight_no_str = f" ({flight_no})" if flight_no else ""
    return f"[{cname}{flight_no_str}] {dep}~{arr} ({dur}, {rtype})"

def _amadeus_details(offer: Dict[str, Any]) -> Tuple[str, str]:
    try:
        det = offer["travelerPricings"][0]["fareDetailsBySegment"][0]
        cabin = CABIN_MAP_AMADEUS.get(det.get("cabin", "ECONOMY"), "일반석")
        bag = det.get("includedCheckedBags", {})
        bag_str = ""
        if "quantity" in bag: bag_str = f"🧳{bag['quantity']}개"
        elif "weight" in bag: bag_str = f"🧳{bag['weight']}kg"
        return cabin, bag_str
    except: return "일반석", ""

def _search_amadeus(origin, dest, date, **kwargs) -> List[Dict]:
    if not _amadeus: return []
    req = {
        "originLocationCode": origin, "destinationLocationCode": dest,
        "departureDate": date, "adults": kwargs.get("adults", 1),
        "currencyCode": "KRW", "max": kwargs.get("max_results", 7)
    }
    if kwargs.get("return_date"): req["returnDate"] = kwargs["return_date"]
    if kwargs.get("travelClass"): req["travelClass"] = kwargs["travelClass"]
    if kwargs.get("includedAirlineCodes"): req["includedAirlineCodes"] = kwargs["includedAirlineCodes"]
    if kwargs.get("nonStop"): req["nonStop"] = True
    if kwargs.get("maxPrice"): req["maxPrice"] = kwargs["maxPrice"]
    
    try:
        r = _amadeus.shopping.flight_offers_search.get(**req)
        return r.data if r else []
    except Exception as e:
        print(f"❌ [Amadeus Error] {e}")
        return []

def _render_amadeus_offers(offers: List[Dict], is_roundtrip: bool) -> List[RenderedFlight]:
    rendered = []
    for o in offers:
        try:
            price = int(float((o.get("price") or {}).get("total") or 0))
            cabin, bag = _amadeus_details(o)
            itin = o.get("itineraries", [])
            if is_roundtrip and len(itin) < 2: continue
            
            out_info = _amadeus_flight_info(itin[0])
            bag_disp = f" | {bag}" if bag else ""
            
            if len(itin) > 1:
                in_info = _amadeus_flight_info(itin[1])
                txt = f"🎫[Amadeus/{cabin}] (왕복)\n   🛫 가는편: {out_info}\n   🛬 오는편: {in_info}{bag_disp}"
                key = f"A|RT|{out_info}|{in_info}|{price}"
            else:
                txt = f"🎫[Amadeus/{cabin}] (편도)\n   🛫 {out_info}{bag_disp}"
                key = f"A|OW|{out_info}|{price}"
            
            rendered.append(RenderedFlight("Amadeus", price, txt, key))
        except: continue
    return rendered

# ---------------------------------------------------------
# 4) Google logic
# ---------------------------------------------------------
def _google_request(params: Dict, timeout=20) -> Dict:
    if not SERPAPI_KEY: return {}
    params = dict(params)
    params.update({"engine": "google_flights", "api_key": SERPAPI_KEY})
    try:
        resp = requests.get(SERPAPI_ENDPOINT, params=params, timeout=timeout)
        return _safe_json(resp)
    except: return {}

def _build_google_params(origin, dest, date, return_date, flight_type, **kwargs) -> Dict:
    p = {
        "departure_id": origin, "arrival_id": dest, "outbound_date": date,
        "type": flight_type, "hl": "ko", "gl": "kr", "currency": "KRW",
        "adults": kwargs.get("adults", 1),
        "travel_class": CABIN_TO_GOOGLE_TRAVEL_CLASS.get((kwargs.get("cabin") or "ECONOMY"), 1)
    }
    if flight_type == "1": p["return_date"] = return_date
    if kwargs.get("nonStop"): p["stops"] = 1
    if kwargs.get("maxPrice"): p["max_price"] = kwargs["maxPrice"]
    if kwargs.get("include_airlines"): p["include_airlines"] = kwargs["include_airlines"]
    return p

def _google_leg_summary(legs: List[Dict]) -> Tuple[str, str, str, str, Optional[int]]:
    if not legs: return ("Unknown", "", "", "", None)
    first, last = legs[0], legs[-1]
    airline = first.get("airline") or "Unknown"
    dep = _leg_time(first, "departure_airport")
    arr = _leg_time(last, "arrival_airport")
    stops = max(len(legs)-1, 0)
    rtype = "직항" if stops == 0 else f"{stops}회 경유"
    dur = _sum_duration_minutes(legs)
    return airline, dep, arr, rtype, dur

def _render_google_items(data: Dict, origin, dest, is_roundtrip) -> List[RenderedFlight]:
    raw = data.get("best_flights") or data.get("other_flights") or []
    items = []
    
    # 2단계(왕복) 파싱 로직은 복잡하여 핵심만 요약: 
    # 실제로는 _render_google_roundtrip_two_step 함수가 필요하지만,
    # 여기서는 "단일 호출"로 온 데이터(편도 등) 처리를 기본으로 하되, 
    # 왕복 2-step은 아래 search_flight_offers에서 호출 구조를 유지합니다.
    
    # 편도 처리용 (왕복 2-step은 별도 함수 사용)
    for f in raw:
        legs = f.get("flights") or []
        if not legs or not _route_matches_google(legs, origin, dest): continue
        
        p = parse_google_price(f)
        air, dep, arr, rtype, dur = _google_leg_summary(legs)
        dur_txt = f"{dur}분" if dur else ""
        
        txt = f"🎫[Google] (편도)\n   🛫 {air} {dep} → {arr} ({dur_txt}, {rtype})"
        key = f"G|OW|{origin}|{dest}|{dep}|{arr}|{p}"
        items.append(RenderedFlight("Google", p, txt, key))
    return items

# Google 왕복 2-step 로직 (기존 코드 유지)
def _render_google_roundtrip_two_step(origin, dest, date, r_date, **kwargs) -> List[RenderedFlight]:
    base = _build_google_params(origin, dest, date, r_date, "1", **kwargs)
    first = _google_request(base)
    out_cands = first.get("best_flights") or first.get("other_flights") or []
    
    combos = []
    for out_f in out_cands[:7]:
        out_legs = out_f.get("flights") or []
        if not _route_matches_google(out_legs, origin, dest): continue
        token = out_f.get("departure_token")
        if not token: continue
        
        out_air, out_dep, out_arr, out_rt, out_dur = _google_leg_summary(out_legs)
        out_dur_s = f"{out_dur}분" if out_dur else ""
        
        sec_p = dict(base)
        sec_p["departure_token"] = token
        second = _google_request(sec_p)
        in_cands = second.get("best_flights") or second.get("other_flights") or []
        
        for in_f in in_cands[:7]:
            in_legs = in_f.get("flights") or []
            if not _route_matches_google(in_legs, dest, origin): continue
            
            in_air, in_dep, in_arr, in_rt, in_dur = _google_leg_summary(in_legs)
            in_dur_s = f"{in_dur}분" if in_dur else ""
            
            p = parse_google_price(in_f) or parse_google_price(out_f)
            txt = (f"🎫[Google] (왕복)\n"
                   f"   🛫 {out_air} {out_dep} → {out_arr} ({out_dur_s}, {out_rt})\n"
                   f"   🛬 {in_air} {in_dep} → {in_arr} ({in_dur_s}, {in_rt})")
            key = f"G|RT|{origin}|{dest}|{out_dep}|{in_dep}|{p}"
            combos.append(RenderedFlight("Google", p, txt, key))
            
    return combos

# ---------------------------------------------------------
# 5) Main Entrypoint (Top 5 Merged)
# ---------------------------------------------------------
def search_flight_offers(
    origin: str,
    destination: str,
    date: str,
    return_date: Optional[str] = None,
    **search_options: Any,
) -> str:
    """
    Amadeus와 Google Flights 결과를 모두 검색한 뒤,
    최저가 순으로 정렬하여 상위 5개(Top 5)만 통합해서 보여줍니다.
    """
    origin = (origin or "").strip().upper()
    destination = (destination or "").strip().upper()
    
    # 옵션 파싱
    adults = int(search_options.get("adults") or 1)
    travelClass = (search_options.get("travelClass") or "ECONOMY").upper()
    includedAirlineCodes = search_options.get("includedAirlineCodes")
    nonStop = search_options.get("nonStop")
    maxPrice = search_options.get("maxPrice")
    timeout = 20
    
    is_roundtrip = bool(return_date)
    
    # 1. Amadeus 검색
    amadeus_raw = _search_amadeus(
        origin, destination, date, 
        return_date=return_date, adults=adults, travelClass=travelClass,
        includedAirlineCodes=includedAirlineCodes, nonStop=nonStop, maxPrice=maxPrice
    )
    amadeus_items = _render_amadeus_offers(amadeus_raw, is_roundtrip)

    # 2. Google Flights 검색
    google_items = []
    try:
        common_kwargs = {
            "adults": adults, "cabin": travelClass, "nonStop": nonStop,
            "maxPrice": maxPrice, "include_airlines": includedAirlineCodes,
            "timeout": timeout
        }
        
        if is_roundtrip:
            google_items = _render_google_roundtrip_two_step(origin, destination, date, return_date, **common_kwargs)
        else:
            # 편도 파라미터 빌드 및 요청
            p_params = _build_google_params(origin, destination, date, None, "2", **common_kwargs)
            p_data = _google_request(p_params, timeout=timeout)
            google_items = _render_google_items(p_data, origin, destination, False)
            
    except Exception as e:
        print(f"❌ Google Search Error: {e}")

    # 3. 통합 및 정렬 (Merge & Sort)
    all_items = amadeus_items + google_items
    
    if not all_items:
        return "조건에 맞는 항공권을 찾을 수 없습니다. (Amadeus/Google)"

    # 중복 제거 (key 기준)
    unique_map = {}
    for item in all_items:
        if item.key not in unique_map:
            unique_map[item.key] = item
    
    merged_list = list(unique_map.values())
    
    # 가격 오름차순 정렬 (가격 0원인 건 맨 뒤로)
    merged_list.sort(key=lambda x: x.price if x.price > 0 else 999999999)
    
    # 4. 상위 10개만 추출 (Top 10)
    final_top_10 = merged_list[:10]
    
    lines = [f"🏆 **통합 최저가 항공권 TOP {len(final_top_10)}**"]
    for i, item in enumerate(final_top_10):
        price_str = _fmt_price(item.price)
        lines.append(f"{i+1}. {item.text} | 💰 {price_str}")
        
    return "\n\n".join(lines)