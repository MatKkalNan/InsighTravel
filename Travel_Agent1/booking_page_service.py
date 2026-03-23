# booking_page_service.py
# ---------------------------------------------------------
# 가짜 예약 웹사이트 기능을 위한 서비스 모듈
# - 예약 요청 시 실시간으로 검색 API를 호출하여 데이터 수집
# - 가짜 예약 확인번호 생성 및 기록
# ---------------------------------------------------------

import uuid
import json
from datetime import datetime
from typing import Any, Dict, List, Optional


class BookingStore:
    """
    인메모리 예약 데이터 저장소.
    - 예약 요청 시 임시로 검색 결과를 저장 (해당 세션에서만 사용)
    - 가짜 예약 확인 기록 관리
    """

    def __init__(self):
        # session_id -> 임시 검색 결과 (예약 요청 시에만 저장)
        self._temp_data: Dict[str, Dict[str, Any]] = {}
        # booking_id -> 예약 확인 기록
        self._bookings: Dict[str, Dict] = {}

    # ---- 임시 데이터 저장 (예약 요청 시에만 사용) ----
    def save_temp_data(self, session_id: str, booking_type: str, items: List[Dict]):
        """예약 요청이 들어왔을 때, 검색 결과를 임시 저장"""
        if session_id not in self._temp_data:
            self._temp_data[session_id] = {}
        self._temp_data[session_id][booking_type] = items

    def get_temp_data(self, session_id: str, booking_type: str) -> List[Dict]:
        """임시 저장된 검색 결과 반환"""
        return self._temp_data.get(session_id, {}).get(booking_type, [])

    def clear_temp_data(self, session_id: str):
        """예약 완료 후 임시 데이터 정리"""
        self._temp_data.pop(session_id, None)

    # ---- 예약 확인 ----
    def confirm_booking(self, session_id: str, booking_type: str,
                        item_index: int, passenger_info: Dict) -> Dict:
        """가짜 예약 확인번호 생성 및 기록"""
        items = self.get_temp_data(session_id, booking_type)
        item = items[item_index] if item_index < len(items) else {}

        # 왕복 항공권인 경우 출국편 + 귀국편 두 개의 예약을 생성
        if booking_type == "flight" and passenger_info.get("is_roundtrip"):
            now = datetime.now().isoformat()

            outbound_id = f"BK-{uuid.uuid4().hex[:8].upper()}"
            outbound = {
                "booking_id": outbound_id,
                "type": booking_type,
                "item": item,
                "passenger_info": passenger_info,
                "status": "confirmed",
                "created_at": now,
            }
            self._bookings[outbound_id] = outbound

            return_id = f"BK-{uuid.uuid4().hex[:8].upper()}"
            return_booking = {
                "booking_id": return_id,
                "type": booking_type,
                "item": item,
                "passenger_info": passenger_info,
                "status": "confirmed",
                "created_at": now,
            }
            self._bookings[return_id] = return_booking

            return {
                "booking_id": outbound_id,
                "return_booking_id": return_id,
                "type": booking_type,
                "item": item,
                "passenger_info": passenger_info,
                "status": "confirmed",
                "created_at": now,
            }

        # 편도 / 호텔 (기존과 동일)
        booking_id = f"BK-{uuid.uuid4().hex[:8].upper()}"
        booking = {
            "booking_id": booking_id,
            "type": booking_type,
            "item": item,
            "passenger_info": passenger_info,
            "status": "confirmed",
            "created_at": datetime.now().isoformat(),
        }
        self._bookings[booking_id] = booking
        return booking

    def get_booking(self, booking_id: str) -> Optional[Dict]:
        """예약 확인번호로 예약 조회"""
        return self._bookings.get(booking_id)


# 싱글톤 인스턴스 (서버 전체에서 공유)
booking_store = BookingStore()