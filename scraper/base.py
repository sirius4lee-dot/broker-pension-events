"""공통 도구: 이벤트 모델, 날짜 파싱, 연금/ISA 분류, 텍스트 줄 파서, 브라우저/HTTP 헬퍼."""
from __future__ import annotations

import html as htmllib
import re
from dataclasses import dataclass, field, asdict
from datetime import date, datetime
from zoneinfo import ZoneInfo

import requests

KST = ZoneInfo("Asia/Seoul")
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/130.0 Safari/537.36")


def today_kst() -> date:
    # GitHub runner는 UTC라 date.today()를 쓰면 KST 새벽에 하루 밀림
    return datetime.now(KST).date()


@dataclass
class Event:
    broker: str
    title: str
    url: str
    start: str | None = None   # YYYY-MM-DD
    end: str | None = None
    desc: str = ""
    category: str = ""
    source: str = "공식"        # 공식 / 배너 / 뉴스

    @property
    def key(self) -> str:
        return f"{self.broker}|{re.sub(r'[^0-9A-Za-z가-힣]', '', self.title)}"

    def to_dict(self) -> dict:
        d = asdict(self)
        d["key"] = self.key
        return d


# ---------- 분류 ----------
CATEGORY_RULES = [
    ("ISA", re.compile(r"ISA", re.I)),
    ("IRP·퇴직연금", re.compile(r"IRP|퇴직연금|\bDC\b|\bDB\b|퇴직", re.I)),
    ("연금저축", re.compile(r"연금저축|개인연금|연금")),
    ("절세계좌", re.compile(r"세제혜택|절세|세액공제|연말정산")),
]


def classify(text: str) -> str | None:
    """연금/ISA 관련이면 분류명, 아니면 None. 여러 개면 ' / '로 묶음."""
    hits = [name for name, rx in CATEGORY_RULES if rx.search(text)]
    if not hits:
        return None
    # '절세계좌'는 다른 분류가 없을 때만
    if len(hits) > 1 and "절세계좌" in hits:
        hits.remove("절세계좌")
    # IRP·퇴직연금이 잡혔으면 일반 '연금' 매칭으로 생긴 연금저축은 실제 '연금저축/개인연금'일 때만 유지
    if "IRP·퇴직연금" in hits and "연금저축" in hits and not re.search(r"연금저축|개인연금", text):
        hits.remove("연금저축")
    return " / ".join(hits)


# ---------- 날짜 ----------
_D = r"(\d{4})\s*[./\-]\s*(\d{1,2})\s*[./\-]\s*(\d{1,2})\.?"
RANGE_RX = re.compile(_D + r"\s*[~∼～\-]\s*" + _D)


def parse_range(text: str, line_mode: bool = False):
    """날짜 범위를 (시작, 끝) ISO 문자열로. line_mode면 '기간 :' 같은 접두어만 허용(제목 속 날짜 무시)."""
    m = RANGE_RX.search(text)
    if not m:
        return None
    if line_mode and re.sub(r"이벤트|기간|[\s:：()\[\]]", "", text[:m.start()]):
        return None
    y1, m1, d1, y2, m2, d2 = map(int, m.groups())
    try:
        return date(y1, m1, d1).isoformat(), date(y2, m2, d2).isoformat()
    except ValueError:
        return None


# ---------- 텍스트 줄 파서 ----------
JUNK_RX = re.compile(
    r"^(진행\s*중|준비\s*중|마감\s*임박|NEW|HOT|D-\d+|자세히\s*보기|더보기|이벤트\s*보기|"
    r"대상.*|종료\s*\d+일전|조회수.*|\d+)$", re.I)


def parse_lines(lines: list[str], broker: str, url: str, before: int = 2,
                labels: set[str] = frozenset()) -> list[Event]:
    """날짜 범위가 있는 줄을 기준으로 앞쪽 `before`개의 의미 있는 줄을 제목/설명으로 사용."""
    events = []
    for i, line in enumerate(lines):
        rng = parse_range(line, line_mode=True)
        if not rng:
            continue
        picked, label = [], ""
        j = i - 1
        while j >= 0 and len(picked) < before:
            cand = lines[j].strip()
            j -= 1
            if not cand:
                continue
            if parse_range(cand, line_mode=True):
                break
            if cand in labels:
                label = cand
                continue
            if JUNK_RX.match(cand):
                continue
            picked.append(cand)
        if j >= 0 and lines[j].strip() in labels and not label:
            label = lines[j].strip()
        if not picked:
            continue
        picked.reverse()
        title, desc = picked[0], " ".join(picked[1:])
        events.append(Event(broker=broker, title=title, desc=desc, url=url,
                            start=rng[0], end=rng[1], category=label))
    return events


def clean_lines(text: str) -> list[str]:
    return [re.sub(r"\s+", " ", l).strip() for l in text.splitlines() if l.strip()]


def html_to_lines(html: str) -> list[str]:
    html = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", html)
    html = re.sub(r"(?i)<br\s*/?>|</(p|div|li|dd|dt|tr|h\d|span|a|em|strong)>", "\n", html)
    text = htmllib.unescape(re.sub(r"<[^>]+>", " ", html))
    return clean_lines(text)


def http_get(url: str, encoding: str | None = None, **kw) -> str:
    r = requests.get(url, headers={"User-Agent": UA}, timeout=30, **kw)
    r.raise_for_status()
    if encoding:
        r.encoding = encoding
    return r.text


def dedupe(events: list[Event]) -> list[Event]:
    seen, out = set(), []
    for e in events:
        if e.key not in seen:
            seen.add(e.key)
            out.append(e)
    return out


class Browser:
    """Playwright Chromium 하나를 여러 증권사가 공유."""

    def __init__(self):
        from playwright.sync_api import sync_playwright
        self._pw = sync_playwright().start()
        self._browser = self._pw.chromium.launch()

    def page_text(self, url: str, frame_contains: str | None = None, wait_ms: int = 4000,
                  click_more: str | None = None, max_clicks: int = 10) -> str:
        ctx = self._browser.new_context(locale="ko-KR", user_agent=UA,
                                        viewport={"width": 1400, "height": 1000})
        try:
            page = ctx.new_page()
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=45000)
            except Exception:
                page.wait_for_timeout(3000)  # 일시적 타임아웃이면 한 번 더
                page.goto(url, wait_until="domcontentloaded", timeout=45000)
            try:
                page.wait_for_load_state("networkidle", timeout=15000)
            except Exception:
                pass
            page.wait_for_timeout(wait_ms)
            target = page.main_frame
            if frame_contains:
                for _ in range(10):
                    fr = [f for f in page.frames if frame_contains in f.url]
                    if fr:
                        target = fr[-1]
                        break
                    page.wait_for_timeout(1000)
                else:
                    raise RuntimeError(f"frame '{frame_contains}' 을 찾지 못함")
            if click_more:
                for _ in range(max_clicks):
                    btn = target.locator(f"text={click_more}").first
                    if not btn.count() or not btn.is_visible():
                        break
                    btn.click()
                    page.wait_for_timeout(1500)
            return target.evaluate("() => document.body ? document.body.innerText : ''")
        finally:
            ctx.close()

    def close(self):
        self._browser.close()
        self._pw.stop()
