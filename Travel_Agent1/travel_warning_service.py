from __future__ import annotations

import os
import requests
from typing import Any, Dict, List, Optional

BASE_API_URL = "https://apis.data.go.kr/1262000"
SERVICE_KEY = os.getenv("PUBLIC_DATA_SERVICE_KEY")
OFFICIAL_SITE_URL = "https://www.0404.go.kr/"


# ---------------------------------------------------------
# 공통 유틸
# ---------------------------------------------------------
def _safe_json(resp: requests.Response) -> Dict[str, Any]:
    try:
        return resp.json()
    except Exception:
        return {
            "error": "Non-JSON response",
            "status": resp.status_code,
            "raw": resp.text[:1000],
        }


def _request(path: str, params: Dict[str, Any], timeout: int = 20) -> Dict[str, Any]:
    if not SERVICE_KEY:
        return {"status": "error", "error": "PUBLIC_DATA_SERVICE_KEY is missing"}

    query = {
        "serviceKey": SERVICE_KEY,
        "pageNo": 1,
        "numOfRows": 300,
        **params,
    }

    try:
        resp = requests.get(f"{BASE_API_URL}{path}", params=query, timeout=timeout)
        data = _safe_json(resp)

        if resp.status_code >= 400:
            return {
                "status": "error",
                "http_status": resp.status_code,
                "data": data,
                "request": query,
            }

        return {
            "status": "ok",
            "data": data,
            "request": query,
        }

    except requests.RequestException as e:
        return {
            "status": "error",
            "error": f"request_failed: {e}",
            "request": query,
        }


def _extract_items(data: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    V3 응답 구조:
    {
      "response": {
        "body": {
          "items": {
            "item": [...]
          }
        }
      }
    }
    """
    try:
        item = data["response"]["body"]["items"]["item"]
        if isinstance(item, list):
            return item
        if isinstance(item, dict):
            return [item]
        return []
    except Exception:
        return []


def _normalize_country_name(country_name: str) -> str:
    return (country_name or "").strip()


def _find_country_item(country_name: str, items: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    target = _normalize_country_name(country_name)

    # 1차: 정확 일치
    for item in items:
        if _normalize_country_name(item.get("country_name", "")) == target:
            return item

    # 2차: 부분 일치
    for item in items:
        name = _normalize_country_name(item.get("country_name", ""))
        if target and (target in name or name in target):
            return item

    return None


# ---------------------------------------------------------
# API 조회
# ---------------------------------------------------------
def get_travel_warning_raw() -> Dict[str, Any]:
    """
    일단 전체 국가 목록을 가져와서 Python에서 country_name으로 필터링.
    데모 기준으로 가장 안정적인 방식.
    """
    return _request("/TravelWarningServiceV3/getTravelWarningListV3", {})


# ---------------------------------------------------------
# 요약 로직
# ---------------------------------------------------------
def summarize_warning(item: Dict[str, Any]) -> Dict[str, Any]:
    summary = {
        "country": item.get("country_name", ""),
        "country_en": item.get("country_en_name", ""),
        "continent": item.get("continent", ""),
        "written_dt": item.get("wrt_dt"),
        "safe": True,
        "high_risk": [],
        "caution": [],
        "raw": item,
    }

    # 1단계: 여행유의
    if item.get("attention") or item.get("attention_partial"):
        summary["caution"].append(
            {
                "level": 1,
                "name": item.get("attention_partial") or item.get("attention"),
                "note": item.get("attention_note", ""),
            }
        )

    # 2단계: 여행자제
    if item.get("control") or item.get("control_partial"):
        summary["caution"].append(
            {
                "level": 2,
                "name": item.get("control_partial") or item.get("control"),
                "note": item.get("control_note", ""),
            }
        )

    # 3단계: 출국권고/철수권고
    if item.get("limita") or item.get("limita_partial"):
        summary["safe"] = False
        summary["high_risk"].append(
            {
                "level": 3,
                "name": item.get("limita_partial") or item.get("limita"),
                "note": item.get("limita_note", ""),
            }
        )

    # 4단계: 여행금지
    if item.get("ban_yna") or item.get("ban_yn_partial"):
        summary["safe"] = False
        summary["high_risk"].append(
            {
                "level": 4,
                "name": item.get("ban_yn_partial") or item.get("ban_yna"),
                "note": item.get("ban_note", ""),
            }
        )

    return summary


def get_country_travel_warning(country_name: str) -> Dict[str, Any]:
    raw = get_travel_warning_raw()

    if raw.get("status") != "ok":
        return {
            "status": "error",
            "message": "여행경보 API 조회 실패",
            "evidence": {
                "api_result": raw,
                "official_site": OFFICIAL_SITE_URL,
            },
        }

    items = _extract_items(raw.get("data", {}))
    if not items:
        return {
            "status": "error",
            "message": "응답에서 국가 목록을 추출하지 못함",
            "evidence": {
                "api_result": raw,
                "official_site": OFFICIAL_SITE_URL,
            },
        }

    item = _find_country_item(country_name, items)
    if not item:
        return {
            "status": "not_found",
            "message": f"'{country_name}' 국가를 찾지 못함",
            "evidence": {
                "official_site": OFFICIAL_SITE_URL,
            },
        }

    summary = summarize_warning(item)

    return {
        "status": "ok",
        "summary": summary,
        "evidence": {
            "official_site": OFFICIAL_SITE_URL,
            "country_image": item.get("img_url_2") or item.get("img_url"),
        },
    }


# ---------------------------------------------------------
# 사용자 응답 렌더링
# ---------------------------------------------------------
def render_travel_warning(country_name: str) -> str:
    result = get_country_travel_warning(country_name)

    if result.get("status") == "error":
        return (
            f"'{country_name}'의 여행경보 정보를 조회하지 못했습니다.\n"
            "잠시 후 다시 시도해 주세요.\n"
            f"최신 정보는 외교부 해외안전여행 공식 사이트({OFFICIAL_SITE_URL})를 꼭 확인해 주세요."
        )

    if result.get("status") == "not_found":
        return (
            f"'{country_name}'에 대한 여행경보 정보를 찾지 못했습니다.\n"
            "국가명을 조금 더 정확히 입력해 주세요.\n"
            f"최신 정보는 외교부 해외안전여행 공식 사이트({OFFICIAL_SITE_URL})를 꼭 확인해 주세요."
        )

    summary = result["summary"]

    country = summary["country"]
    continent = summary["continent"]
    high_risk = summary["high_risk"]
    caution = summary["caution"]
    written_dt = summary.get("written_dt")

    lines = [f"🛡️ **{country} 여행경보 정보**"]

    if continent:
        lines.append(f"- 대륙: {continent}")

    if summary["safe"]:
        lines.append("- 현재 조회 기준으로 출국권고(3단계) 이상 또는 여행금지 지역은 확인되지 않았습니다.")
        if caution:
            lines.append("- 다만 일부 지역에는 여행유의(1단계) 또는 여행자제(2단계)가 적용될 수 있습니다.")
    else:
        lines.append("⚠️ **권고 이상 경보가 발령된 지역이 있습니다.**")
        for item in high_risk:
            lines.append(f"- {item['name']}")
            if item["note"]:
                lines.append(f"  사유/대상 지역: {item['note']}")

    if caution:
        lines.append("ℹ️ **주의가 필요한 단계**")
        for item in caution:
            note = f" / {item['note']}" if item.get("note") else ""
            lines.append(f"- {item['name']}{note}")

    if written_dt:
        lines.append(f"- 기준일: {written_dt}")

    lines.append("")
    lines.append(
        f"신뢰할 수 있는 공식 데이터를 바탕으로 안내했지만, 출발 전에는 외교부 해외안전여행 공식 사이트({OFFICIAL_SITE_URL})를 꼭 다시 확인해 주세요."
    )

    return "\n".join(lines)