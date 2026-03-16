# transportation_service.py
from __future__ import annotations

import os
import requests
from dataclasses import dataclass
from typing import Any, Dict, Optional, List, Tuple

ROUTES_ENDPOINT = "https://routes.googleapis.com/directions/v2:computeRoutes"

DEFAULT_FIELD_MASK = (
    "routes.duration,"
    "routes.distanceMeters,"
    "routes.legs.steps.navigationInstruction,"
    "routes.legs.steps.travelMode,"
    "routes.legs.steps.transitDetails"
)

@dataclass
class TransportOption:
    mode: str
    duration_sec: int
    distance_m: int
    summary: str

MODE_ALIASES = {
    "WALK": "WALK", "WALKING": "WALK", "도보": "WALK",
    "TRANSIT": "TRANSIT", "대중교통": "TRANSIT", "지하철": "TRANSIT", "버스": "TRANSIT",
    "DRIVE": "DRIVE", "CAR": "DRIVE", "자동차": "DRIVE", "택시": "DRIVE",
    "BICYCLE": "BICYCLE", "자전거": "BICYCLE",
    "ALL": "ALL", "전체": "ALL",
}

def normalize_mode(mode: Optional[str]) -> str:
    if not mode:
        return "ALL"
    s = mode.strip()
    up = s.upper()
    return MODE_ALIASES.get(up) or MODE_ALIASES.get(s) or "ALL"

def _get_maps_key() -> Optional[str]:
    return os.getenv("GOOGLE_MAPS_API_KEY")

def _safe_json(resp: requests.Response) -> Dict[str, Any]:
    try:
        return resp.json()
    except Exception:
        return {"error": "Non-JSON response", "status": resp.status_code, "raw": resp.text[:1000]}

def _fmt_duration(seconds: int) -> str:
    if not seconds or seconds <= 0:
        return "정보없음"
    m = seconds // 60
    h = m // 60
    m = m % 60
    return f"{h}시간 {m}분" if h else f"{m}분"

def _parse_duration_to_sec(duration_val: Any) -> int:
    if isinstance(duration_val, str) and duration_val.endswith("s"):
        try:
            return int(float(duration_val[:-1]))
        except Exception:
            return 0
    if isinstance(duration_val, (int, float)):
        return int(duration_val)
    return 0

def _summarize_transit_steps(route: Dict[str, Any], max_items: int = 3) -> str:
    """
    TRANSIT일 때 steps[].transitDetails를 최대 3개까지 요약.
    응답 포맷이 케이스별로 다를 수 있어서 '있으면 뽑고 없으면 빈값' 스타일로 방어.
    """
    legs = route.get("legs") or []
    if not legs:
        return ""
    steps = (legs[0] or {}).get("steps") or []
    items: List[str] = []

    for st in steps:
        td = st.get("transitDetails")
        if not isinstance(td, dict):
            continue

        line = td.get("transitLine") or {}
        vehicle = (line.get("vehicle") or {}).get("type") or ""
        short = line.get("nameShort") or line.get("name") or ""
        headsign = td.get("headsign") or ""
        num_stops = td.get("stopCount")

        part = []
        if vehicle: part.append(str(vehicle))
        if short: part.append(str(short))
        if headsign: part.append(f"({headsign} 방향)")
        if isinstance(num_stops, int): part.append(f"{num_stops}정거장")
        if part:
            items.append(" ".join(part))
        if len(items) >= max_items:
            break

    return " / ".join(items)

def compute_route(
    origin: str,
    destination: str,
    mode: str = "TRANSIT",
    departure_time_iso: Optional[str] = None,
    language_code: str = "ko-KR",
    timeout: int = 20,
) -> Dict[str, Any]:
    api_key = _get_maps_key()
    if not api_key:
        return {"status": "error", "error": "GOOGLE_MAPS_API_KEY is missing"}

    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": api_key,
        "X-Goog-FieldMask": DEFAULT_FIELD_MASK,
    }

    body: Dict[str, Any] = {
        "origin": {"address": origin},
        "destination": {"address": destination},
        "travelMode": mode,
        "languageCode": language_code,
    }

    if departure_time_iso:
        body["departureTime"] = departure_time_iso

    resp = requests.post(ROUTES_ENDPOINT, headers=headers, json=body, timeout=timeout)
    data = _safe_json(resp)
    if resp.status_code >= 400:
        return {"status": "error", "http_status": resp.status_code, "data": data, "request": body}
    
    print("[compute_route]", body)
    print("[compute_route_status]", resp.status_code, data)
    
    return {"status": "ok", "data": data, "request": body}

def render_transport_options(
    origin: str,
    destination: str,
    mode: Optional[str] = None,
    modes: Optional[List[str]] = None,
    departure_time_iso: Optional[str] = None,
    include_evidence: bool = False,
) -> str:
    # 1) mode 우선. mode가 없을 때만 modes 사용. 둘 다 없으면 ALL.
    if mode is None and modes:
        # 호출자가 modes를 명시한 경우 존중
        modes_to_try = modes
    else:
        nm = normalize_mode(mode)
        if nm == "ALL":
            modes_to_try = ["TRANSIT", "WALK", "DRIVE"]
        else:
            modes_to_try = [nm]

    options: List[TransportOption] = []
    failures: List[str] = []
    evidences: List[Dict[str, Any]] = []

    for m in modes_to_try:
        r = compute_route(origin, destination, mode=m, departure_time_iso=departure_time_iso)

        if r.get("status") != "ok":
            failures.append(f"- {m}: API 오류/실패")
            evidences.append({"mode": m, "error": r.get("error") or r.get("data")})
            continue

        routes = (r["data"] or {}).get("routes") or []
        if not routes:
            # 모드별 실패 안내를 다르게
            if m == "WALK":
                failures.append(f"- {m}: 보행 경로가 제공되지 않거나(또는 매칭이 불명확) 경로가 없어요.")
            else:
                failures.append(f"- {m}: 경로가 없어요(장소명/매칭 문제일 수 있음).")
            evidences.append({"mode": m, "no_routes": True, "request": r.get("request")})
            continue

        top = routes[0]
        dur_s = _parse_duration_to_sec(top.get("duration"))
        dist_m = int(top.get("distanceMeters") or 0)

        extra = ""
        if m == "TRANSIT":
            t = _summarize_transit_steps(top)
            if t:
                extra = f" | {t}"

        summary = f"예상 {_fmt_duration(dur_s)}, {dist_m/1000:.1f}km{extra}"
        options.append(TransportOption(m, dur_s, dist_m, summary))
        evidences.append({"mode": m, "request": r.get("request")})

    if not options:
        # ALL이든 단일이든, 실패 원인을 보여주면 디버깅/UX가 좋아짐
        msg = (
            "조건에 맞는 이동 경로를 찾지 못했습니다.\n"
            "가능한 원인:\n"
            + ("\n".join(failures) if failures else "- (원인 파악 실패)\n")
            + "\n\n✅ 시도해볼 것:\n"
            "- 장소명을 더 구체적으로 입력해 주세요 (도시/나라/역/랜드마크 포함)\n"
            "- 가게/상호명 대신 '역/명소/주소'로 입력해 보세요\n"
            "- 교통수단을 바꿔서 다시 검색해 보세요 (대중교통/도보/차량)\n"
        )
        return msg

    # 소요시간 오름차순 정렬
    options.sort(key=lambda x: x.duration_sec if x.duration_sec > 0 else 10**18)

    lines = [f"🧭 **이동 옵션: {origin} → {destination}**"]
    for i, opt in enumerate(options, 1):
        lines.append(f"{i}. **{opt.mode}**: {opt.summary}")

    # ALL 비교 시, 실패한 모드도 보여주면 “왜 1개만?” 오해가 사라짐
    if len(modes_to_try) > 1 and failures:
        lines.append("\n(참고) 경로가 없던 모드:")
        lines.extend(failures)

    if include_evidence:
        lines.append("\n[DEBUG evidence] " + str(evidences[:3]))

    return "\n".join(lines)

def render_transport_batch(
    stops: List[str],
    mode: Optional[str] = "TRANSIT",
    departure_time_iso: Optional[str] = None,
) -> str:
    """
    시나리오 2 대비: [A,B,C,D]가 오면 A->B, B->C, C->D를 순차 계산해 표로 리턴
    """
    if not stops or len(stops) < 2:
        return "이동시간 계산을 위해 최소 2개 이상의 장소가 필요해요."

    nm = normalize_mode(mode)
    if nm == "ALL":
        nm = "TRANSIT"

    lines = ["🗺️ **일정 구간별 이동시간**"]
    total_sec = 0

    for i in range(len(stops) - 1):
        a, b = stops[i], stops[i + 1]
        r = compute_route(a, b, mode=nm, departure_time_iso=departure_time_iso)
        if r.get("status") != "ok":
            lines.append(f"- {a} → {b}: 오류(재시도 필요)")
            continue

        routes = (r["data"] or {}).get("routes") or []
        if not routes:
            lines.append(f"- {a} → {b}: 경로 없음(장소명 구체화 필요)")
            continue

        top = routes[0]
        dur_s = _parse_duration_to_sec(top.get("duration"))
        dist_m = int(top.get("distanceMeters") or 0)
        total_sec += max(dur_s, 0)

        extra = ""
        if nm == "TRANSIT":
            t = _summarize_transit_steps(top)
            if t:
                extra = f" | {t}"

        lines.append(f"- {a} → {b}: {_fmt_duration(dur_s)} ({dist_m/1000:.1f}km){extra}")

    lines.append(f"\n총 이동시간(추정): {_fmt_duration(total_sec)}")
    return "\n".join(lines)