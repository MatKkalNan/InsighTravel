# date_parser.py
import re
from datetime import date, datetime, timedelta
from typing import Optional
from zoneinfo import ZoneInfo

KST = ZoneInfo("Asia/Seoul")

WEEKDAY_MAP = {
    "월": 0,
    "화": 1,
    "수": 2,
    "목": 3,
    "금": 4,
    "토": 5,
    "일": 6,
}


def get_today_kst() -> date:
    return datetime.now(KST).date()


def parse_iso_date(value: str) -> Optional[date]:
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except Exception:
        return None


def normalize_korean_date_text(text: str) -> str:
    """
    날짜 표현 정규화
    - 공백 제거
    - 자주 쓰는 축약 표현 통일
    """
    if not text:
        return ""

    normalized = text.strip().lower()
    normalized = re.sub(r"\s+", "", normalized)

    replacements = {
        "낼": "내일",
        "담주": "다음주",
        "담주말": "다음주말",
        "내일모레": "내일모레",
        "낼모레": "내일모레",
    }

    return replacements.get(normalized, normalized)


def parse_duration(text: str) -> tuple[Optional[int], Optional[int]]:
    if not text:
        return None, None

    nights = None
    days = None

    m_nights = re.search(r"(\d+)\s*박", text)
    m_days = re.search(r"(\d+)\s*일", text)

    if m_nights:
        nights = int(m_nights.group(1))
    if m_days:
        days = int(m_days.group(1))

    return nights, days


def _get_week_start(base_date: date) -> date:
    """해당 주의 월요일"""
    return base_date - timedelta(days=base_date.weekday())


def _get_weekend_start(base_date: date, weeks_ahead: int = 0) -> date:
    """
    기준일이 속한 주에서 weeks_ahead만큼 이동한 뒤 그 주의 토요일 반환
    weeks_ahead=0 -> 이번주말
    weeks_ahead=1 -> 다음주말
    weeks_ahead=2 -> 다다음주말
    """
    target_base = base_date + timedelta(days=7 * weeks_ahead)
    delta = (5 - target_base.weekday()) % 7  # 토요일=5
    return target_base + timedelta(days=delta)


def _resolve_weekday_in_target_week(base_date: date, weekday_kr: str, weeks_ahead: int = 0) -> date:
    """
    기준 주에서 weeks_ahead만큼 이동한 '그 주'의 특정 요일 반환
    예:
    - 이번주 금요일
    - 다음주 화요일
    - 다다음주 월요일
    """
    target_week_start = _get_week_start(base_date) + timedelta(days=7 * weeks_ahead)
    target_weekday = WEEKDAY_MAP[weekday_kr]
    return target_week_start + timedelta(days=target_weekday)


def _resolve_unqualified_weekday(base_date: date, weekday_kr: str) -> date:
    """
    '금요일', '화요일'처럼 이번/다음 주 수식어가 없을 때
    가장 가까운 미래의 해당 요일로 해석
    """
    target_weekday = WEEKDAY_MAP[weekday_kr]
    delta = (target_weekday - base_date.weekday()) % 7
    if delta == 0:
        return base_date
    return base_date + timedelta(days=delta)


def _parse_relative_week_count(normalized_text: str) -> Optional[int]:
    """
    다음주/다다음주/다다다음주/... 를 정수 주차로 변환
    반환:
    - 다음주 -> 1
    - 다다음주 -> 2
    - 다다다음주 -> 3
    """
    if normalized_text == "다음주":
        return 1

    m = re.fullmatch(r"(다+)음주", normalized_text)
    if m:
        da_count = len(m.group(1))
        return da_count

    return None


def _parse_relative_weekend_count(normalized_text: str) -> Optional[int]:
    """
    다음주말/다다음주말/다다다음주말/... 를 정수 주차로 변환
    반환:
    - 다음주말 -> 1
    - 다다음주말 -> 2
    - 다다다음주말 -> 3
    """
    if normalized_text == "다음주말":
        return 1

    m = re.fullmatch(r"(다+)음주말", normalized_text)
    if m:
        da_count = len(m.group(1))
        return da_count

    return None


def resolve_date_expression(expr: str, base_date: Optional[date] = None) -> Optional[date]:
    if not expr:
        return None

    base_date = base_date or get_today_kst()
    raw_text = expr.strip()
    text = normalize_korean_date_text(raw_text)

    # 1) 절대적으로 자주 쓰는 상대 날짜
    simple_relative = {
        "오늘": 0,
        "today": 0,
        "내일": 1,
        "tomorrow": 1,
        "모레": 2,
        "내일모레": 2,
        "글피": 3,
    }
    if text in simple_relative:
        return base_date + timedelta(days=simple_relative[text])

    # 2) 주 단위 기본 표현
    if text == "이번주":
        return _get_week_start(base_date)

    weeks_ahead = _parse_relative_week_count(text)
    if weeks_ahead is not None:
        return _get_week_start(base_date) + timedelta(days=7 * weeks_ahead)

    # 3) 주말 기본 표현
    if text == "이번주말":
        return _get_weekend_start(base_date, weeks_ahead=0)

    weekend_weeks_ahead = _parse_relative_weekend_count(text)
    if weekend_weeks_ahead is not None:
        return _get_weekend_start(base_date, weeks_ahead=weekend_weeks_ahead)

    # 4) "이번주금요일", "다음주화요일", "다다다음주목요일"
    m = re.fullmatch(r"(이번주|(다*)음주)([월화수목금토일])요일?", text)
    if m:
        week_expr = m.group(1)
        da_part = m.group(2)  # 다음주면 "", 다다음주면 "다다"
        weekday_kr = m.group(3)

        if week_expr == "이번주":
            weeks_ahead = 0
        else:
            weeks_ahead = len(da_part) if da_part else 1

        return _resolve_weekday_in_target_week(base_date, weekday_kr, weeks_ahead=weeks_ahead)

    # 5) "금요일", "화요일"
    m = re.fullmatch(r"([월화수목금토일])요일?", text)
    if m:
        weekday_kr = m.group(1)
        return _resolve_unqualified_weekday(base_date, weekday_kr)

    # 6) "4월5일"
    m = re.fullmatch(r"(\d{1,2})월(\d{1,2})일", text)
    if m:
        month = int(m.group(1))
        day = int(m.group(2))
        year = base_date.year

        try:
            candidate = date(year, month, day)
        except ValueError:
            return None

        # 이미 지났으면 내년으로 넘김
        if candidate < base_date:
            try:
                candidate = date(year + 1, month, day)
            except ValueError:
                return None
        return candidate

    # 7) ISO 날짜
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
        return parse_iso_date(text)

    return None


def infer_checkout_or_return(checkin_or_departure: Optional[date], duration_text: str) -> Optional[date]:
    """
    2박 3일:
    - 체크인 4/3 -> 체크아웃 4/5
    - 출발 4/3 -> 귀국 4/5
    """
    if not checkin_or_departure or not duration_text:
        return None

    nights, days = parse_duration(duration_text)

    if nights is not None:
        return checkin_or_departure + timedelta(days=nights)

    if days is not None:
        return checkin_or_departure + timedelta(days=days - 1)

    return None


def sanitize_date_range(
    start_date: Optional[date],
    end_date: Optional[date],
) -> tuple[Optional[date], Optional[date]]:
    today = get_today_kst()

    try:
        max_future = date(today.year + 2, today.month, today.day)
    except ValueError:
        # 윤년/말일 대응
        max_future = today + timedelta(days=365 * 2)

    if start_date and start_date < today:
        start_date = today

    if end_date and end_date < today:
        end_date = today

    if start_date and start_date > max_future:
        start_date = None

    if end_date and end_date > max_future:
        end_date = None

    if start_date and end_date and end_date < start_date:
        end_date = start_date

    return start_date, end_date


def to_iso(d: Optional[date]) -> Optional[str]:
    return d.isoformat() if d else None