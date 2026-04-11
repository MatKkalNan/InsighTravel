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

WEEKDAY_KR_LIST = "월화수목금토일"


def get_today_kst() -> date:
    return datetime.now(KST).date()


def parse_iso_date(value: str) -> Optional[date]:
    if not value:
        return None

    value = value.strip()
    candidates = [
        "%Y-%m-%d",
        "%Y.%m.%d",
        "%Y/%m/%d",
        "%Y-%m-%d",
    ]
    for fmt in candidates:
        try:
            return datetime.strptime(value, fmt).date()
        except Exception:
            pass
    return None


def _safe_date(year: int, month: int, day: int) -> Optional[date]:
    try:
        return date(year, month, day)
    except Exception:
        return None


def normalize_korean_date_text(text: str) -> str:
    """
    날짜 표현 정규화
    - 소문자화
    - 공백 정리
    - 자주 쓰는 축약 통일
    - 조사/어미 제거
    - 날짜 구분자 통일
    """
    if not text:
        return ""

    normalized = text.strip().lower()
    normalized = normalized.replace(" ", " ")
    normalized = re.sub(r"\s+", " ", normalized).strip()

    # 자주 쓰는 표현 통일
    replacements = {
        "낼": "내일",
        "낼모레": "내일모레",
        "내일 모레": "내일모레",
        "담주": "다음주",
        "담주말": "다음주말",
        "담주 월요일": "다음주 월요일",
        "이번 주": "이번주",
        "다음 주": "다음주",
        "다다음 주": "다다음주",
        "이번 주말": "이번주말",
        "다음 주말": "다음주말",
        "다다음 주말": "다다음주말",
        "tomorrow": "내일",
        "today": "오늘",
    }
    normalized = replacements.get(normalized, normalized)

    # 끝 조사/어미 제거
    suffix_patterns = [
        r"(부터는)$",
        r"(부터)$",
        r"(까지는)$",
        r"(까지)$",
        r"(쯤에는)$",
        r"(쯤에)$",
        r"(쯤)$",
        r"(날에)$",
        r"(날)$",
        r"(에)$",
    ]
    for pattern in suffix_patterns:
        normalized = re.sub(pattern, "", normalized).strip()

    # 조사 제거 후 공백 제거 버전도 쓰기 쉬우니 공백도 최종 제거
    normalized = re.sub(r"\s+", "", normalized)

    # 날짜 구분자 통일
    normalized = normalized.replace(".", "-").replace("/", "-")

    # 흔한 표현 보정
    phrase_replacements = {
        "내일부터": "내일",
        "모레부터": "모레",
        "글피부터": "글피",
        "이번주부터": "이번주",
        "다음주부터": "다음주",
        "다다음주부터": "다다음주",
        "이번주말부터": "이번주말",
        "다음주말부터": "다음주말",
        "다다음주말부터": "다다음주말",
    }
    normalized = phrase_replacements.get(normalized, normalized)

    return normalized


def parse_duration(text: str) -> tuple[Optional[int], Optional[int]]:
    """
    예:
    - 2박3일 / 2박 3일
    - 3일
    - 1박
    """
    if not text:
        return None, None

    raw = text.strip()
    raw = re.sub(r"\s+", "", raw)

    nights = None
    days = None

    m_nights = re.search(r"(\d+)박", raw)
    m_days = re.search(r"(\d+)일", raw)

    if m_nights:
        nights = int(m_nights.group(1))
    if m_days:
        days = int(m_days.group(1))

    # "2박"만 있으면 보통 3일로 보지 않고 nights만 사용
    # "3일"만 있으면 checkout은 start + 2일
    return nights, days


def _get_week_start(base_date: date) -> date:
    return base_date - timedelta(days=base_date.weekday())


def _get_weekend_start(base_date: date, weeks_ahead: int = 0) -> date:
    target_base = base_date + timedelta(days=7 * weeks_ahead)
    delta = (5 - target_base.weekday()) % 7  # 토요일
    return target_base + timedelta(days=delta)


def _resolve_weekday_in_target_week(base_date: date, weekday_kr: str, weeks_ahead: int = 0) -> date:
    target_week_start = _get_week_start(base_date) + timedelta(days=7 * weeks_ahead)
    target_weekday = WEEKDAY_MAP[weekday_kr]
    return target_week_start + timedelta(days=target_weekday)


def _resolve_unqualified_weekday(base_date: date, weekday_kr: str) -> date:
    target_weekday = WEEKDAY_MAP[weekday_kr]
    delta = (target_weekday - base_date.weekday()) % 7
    if delta == 0:
        return base_date
    return base_date + timedelta(days=delta)


def _parse_relative_week_count(normalized_text: str) -> Optional[int]:
    if normalized_text == "다음주":
        return 1

    m = re.fullmatch(r"(다+)음주", normalized_text)
    if m:
        return len(m.group(1))

    return None


def _parse_relative_weekend_count(normalized_text: str) -> Optional[int]:
    if normalized_text == "다음주말":
        return 1

    m = re.fullmatch(r"(다+)음주말", normalized_text)
    if m:
        return len(m.group(1))

    return None


def _parse_days_after(text: str, base_date: date) -> Optional[date]:
    m = re.fullmatch(r"(\d+)일(뒤|후)", text)
    if m:
        return base_date + timedelta(days=int(m.group(1)))
    return None


def _parse_weeks_after(text: str, base_date: date) -> Optional[date]:
    m = re.fullmatch(r"(\d+)주(뒤|후)", text)
    if m:
        return base_date + timedelta(days=7 * int(m.group(1)))
    return None


def _parse_month_day(text: str, base_date: date) -> Optional[date]:
    # 4월5일 / 4월05일
    m = re.fullmatch(r"(\d{1,2})월(\d{1,2})일", text)
    if m:
        month = int(m.group(1))
        day = int(m.group(2))
        candidate = _safe_date(base_date.year, month, day)
        if candidate is None:
            return None
        if candidate < base_date:
            candidate = _safe_date(base_date.year + 1, month, day)
        return candidate

    # 4-5 / 04-05  (normalize에서 / . 는 - 로 통일됨)
    m = re.fullmatch(r"(\d{1,2})-(\d{1,2})", text)
    if m:
        month = int(m.group(1))
        day = int(m.group(2))
        candidate = _safe_date(base_date.year, month, day)
        if candidate is None:
            return None
        if candidate < base_date:
            candidate = _safe_date(base_date.year + 1, month, day)
        return candidate

    return None


def _parse_full_year_date(text: str) -> Optional[date]:
    # 2026-04-05 / 2026-4-5 / 2026.4.5 / 2026/4/5 가 normalize 후 2026-4-5 형태 가능
    m = re.fullmatch(r"(\d{4})-(\d{1,2})-(\d{1,2})", text)
    if m:
        return _safe_date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    return None


def _parse_year_month_day_korean(text: str) -> Optional[date]:
    m = re.fullmatch(r"(\d{4})년(\d{1,2})월(\d{1,2})일", text)
    if m:
        return _safe_date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    return None


def _parse_month_only(text: str, base_date: date) -> Optional[date]:
    # "4월초", "4월중순", "4월말"
    m = re.fullmatch(r"(\d{1,2})월(초|중순|말)", text)
    if not m:
        return None

    month = int(m.group(1))
    when = m.group(2)
    day_map = {"초": 5, "중순": 15, "말": 25}
    day = day_map[when]

    candidate = _safe_date(base_date.year, month, day)
    if candidate is None:
        return None
    if candidate < base_date:
        candidate = _safe_date(base_date.year + 1, month, day)
    return candidate


def _parse_special_day_bucket(text: str, base_date: date) -> Optional[date]:
    if text == "주말":
        return _get_weekend_start(base_date, 0)

    if text == "평일":
        # 오늘이 평일이면 오늘, 주말이면 다음 월요일
        if base_date.weekday() < 5:
            return base_date
        return _get_week_start(base_date) + timedelta(days=7)

    return None


def _parse_weekday_range_start(text: str, base_date: date) -> Optional[date]:
    # 금~일 / 토-월 / 화요일~목요일
    m = re.fullmatch(rf"([{WEEKDAY_KR_LIST}])(?:요일)?[~-]([{WEEKDAY_KR_LIST}])(?:요일)?", text)
    if not m:
        return None
    start_day = m.group(1)
    return _resolve_unqualified_weekday(base_date, start_day)


def resolve_date_expression(expr: str, base_date: Optional[date] = None) -> Optional[date]:
    if not expr:
        return None

    base_date = base_date or get_today_kst()
    raw_text = expr.strip()
    text = normalize_korean_date_text(raw_text)

    if not text:
        return None

    simple_relative = {
        "오늘": 0,
        "내일": 1,
        "모레": 2,
        "내일모레": 2,
        "글피": 3,
    }
    if text in simple_relative:
        return base_date + timedelta(days=simple_relative[text])

    # n일 후 / n주 뒤
    parsed = _parse_days_after(text, base_date)
    if parsed:
        return parsed

    parsed = _parse_weeks_after(text, base_date)
    if parsed:
        return parsed

    # 이번주 / 다음주 / 다다음주
    if text == "이번주":
        return _get_week_start(base_date)

    weeks_ahead = _parse_relative_week_count(text)
    if weeks_ahead is not None:
        return _get_week_start(base_date) + timedelta(days=7 * weeks_ahead)

    # 주말
    if text == "이번주말":
        return _get_weekend_start(base_date, weeks_ahead=0)

    weekend_weeks_ahead = _parse_relative_weekend_count(text)
    if weekend_weeks_ahead is not None:
        return _get_weekend_start(base_date, weeks_ahead=weekend_weeks_ahead)

    # "주말", "평일", "4월말"
    parsed = _parse_special_day_bucket(text, base_date)
    if parsed:
        return parsed

    parsed = _parse_month_only(text, base_date)
    if parsed:
        return parsed

    # "이번주금요일", "다음주화요일", "다다다음주목요일"
    m = re.fullmatch(r"(이번주|(다*)음주)([월화수목금토일])요일?", text)
    if m:
        week_expr = m.group(1)
        da_part = m.group(2)
        weekday_kr = m.group(3)

        if week_expr == "이번주":
            weeks_ahead = 0
        else:
            weeks_ahead = len(da_part) if da_part else 1

        return _resolve_weekday_in_target_week(base_date, weekday_kr, weeks_ahead=weeks_ahead)

    # "금요일"
    m = re.fullmatch(r"([월화수목금토일])요일?", text)
    if m:
        return _resolve_unqualified_weekday(base_date, m.group(1))

    # "금~일" -> 시작일만 반환
    parsed = _parse_weekday_range_start(text, base_date)
    if parsed:
        return parsed

    # 2026년4월5일
    parsed = _parse_year_month_day_korean(text)
    if parsed:
        return parsed

    # 2026-4-5 / 2026-04-05
    parsed = _parse_full_year_date(text)
    if parsed:
        return parsed

    # 4월5일 / 4-5
    parsed = _parse_month_day(text, base_date)
    if parsed:
        return parsed

    # 기존 ISO fallback
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
        return parse_iso_date(text)

    return None


def infer_checkout_or_return(checkin_or_departure: Optional[date], duration_text: str) -> Optional[date]:
    """
    - 2박 3일 -> +2일 후 체크아웃
    - 3일 -> +2일 후 체크아웃
    - 1박 -> +1일 후 체크아웃
    """
    if not checkin_or_departure or not duration_text:
        return None

    nights, days = parse_duration(duration_text)

    if nights is not None:
        return checkin_or_departure + timedelta(days=nights)

    if days is not None:
        return checkin_or_departure + timedelta(days=max(days - 1, 0))

    return None


def sanitize_date_range(
    start_date: Optional[date],
    end_date: Optional[date],
) -> tuple[Optional[date], Optional[date]]:
    today = get_today_kst()

    try:
        max_future = date(today.year + 2, today.month, today.day)
    except ValueError:
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