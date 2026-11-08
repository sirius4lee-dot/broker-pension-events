"""증권사별 수집기. 각 함수는 (browser) -> list[Event] 이며, 연금/ISA 필터 전 '전체 이벤트'를 돌려준다.

사이트별로 실제 확인한 방식(2026-11-08 기준):
- 브라우저 렌더링: 한국투자, 삼성(iframe), NH(frameset), KB, 신한(더보기), 하나, 대신
- 정적 HTML: 미래에셋(브라우저로 열면 보안프로그램 설치 페이지로 이동해서 HTTP로 받음)
- 키움: 이벤트 목록 API가 봇 차단(JS 챌린지)이라 우회하지 않고, 메인 배너 데이터(KN_xx.js)만 사용
- 토스: 웹 이벤트 목록이 없어(앱 전용) Google 뉴스 RSS 보도자료로 대체
"""
from __future__ import annotations

import json
import re
import xml.etree.ElementTree as ET
from datetime import timedelta
from email.utils import parsedate_to_datetime
from urllib.parse import quote

from .base import (Browser, Event, clean_lines, dedupe, html_to_lines, http_get,
                   parse_lines, today_kst)


def kis(b: Browser):
    base = "https://securities.koreainvestment.com/main/customer/notice/Event.jsp"
    out = []
    for p in range(1, 8):
        url = f"{base}?gubun=i&cmd=TF04gb010001&currentPage={p}"
        try:
            text = b.page_text(url, wait_ms=1500)
        except Exception:
            if p == 1:
                raise
            break  # 뒤 페이지 실패는 이미 받은 것만 사용 (Actions에서 빈 3페이지가 타임아웃난 적 있음)
        evs = parse_lines(clean_lines(text), "한국투자증권", base + "?gubun=i", before=2)
        new = [e for e in evs if e.key not in {o.key for o in out}]
        if not new:
            break
        out += new
    return out


def mirae(b: Browser):
    base = "https://securities.miraeasset.com/hki/hki7000/r05.do"
    out = []
    for p in range(1, 8):
        html = http_get(f"{base}?currentPage={p}", encoding="euc-kr")
        new = []
        for m in re.finditer(r"doView\('(\d+)'[^)]*\).*?evTit\">\s*([^<]+?)\s*</dd>\s*<dd class=\"evDate\">([^<]*)",
                             html, re.S):
            eid, title, period = m.groups()
            evs = parse_lines([title, period], "미래에셋증권",
                              f"https://securities.miraeasset.com/hki/hki7000/v05.do?cs_ecis_id={eid}", before=1)
            new += [e for e in evs if e.key not in {o.key for o in out}]
        if not new:
            break
        out += new
    return out


def samsung(b: Browser):
    url = "https://www.samsungpop.com/?MENU_CODE=M1231757773125"
    text = b.page_text(url, frame_contains="eventguide/event.do")
    return parse_lines(clean_lines(text), "삼성증권", url, before=2)


def nh(b: Browser):
    url = "https://www.nhsec.com/guestGuide/ctmList/eventIngList.action"
    text = b.page_text(url, frame_contains="eventIngList.action")
    return parse_lines(clean_lines(text), "NH투자증권", url, before=2)


KB_LABELS = {"국내주식", "해외주식", "금융상품", "연금/ISA", "은행연계/비대면", "ETF", "기타"}


def kb(b: Browser):
    url = "https://www.kbsec.com/go.able?linkcd=m06090002"
    return parse_lines(clean_lines(b.page_text(url)), "KB증권", url, before=1, labels=KB_LABELS)


def shinhan(b: Browser):
    url = "https://www.shinhansec.com/siw/customer-center/event/giEvent1/view.do"
    text = b.page_text(url, click_more="더보기")
    return parse_lines(clean_lines(text), "신한투자증권", url, before=1)


def hana(b: Browser):
    url = "https://www.hanaw.com/corebbs5/eventIng/list/list.cmd"
    return parse_lines(clean_lines(b.page_text(url)), "하나증권", url, before=1)


def daishin(b: Browser):
    url = "https://www.daishin.com/g.ds?m=1109&p=12931&v=12831"
    return parse_lines(clean_lines(b.page_text(url)), "대신증권", url, before=2)


_KW_PERIOD = re.compile(r"이벤트\s*기간\s*[:：(]?\s*(\d{2,4})\.(\d{1,2})\.(\d{1,2})\.?\s*[~∼～\-]\s*(\d{2,4})\.(\d{1,2})\.(\d{1,2})")


def kiwoom(b: Browser):
    out = []
    for n in range(1, 9):
        try:
            raw = http_get(f"https://www.kiwoom.com/h/kws/assets/deploy/KN_{n:02d}/data/KN_{n:02d}.js")
            items = json.loads(raw.strip())
        except Exception:
            continue
        for it in items:
            title = re.sub(r"^\[[^\]]*\]", "", (it.get("title") or "").strip())
            href = it.get("href") or "https://www.kiwoom.com/h/customer/event/VIngEventView"
            if not title or "/event/" not in href:
                continue
            out.append(Event(broker="키움증권", title=title, url=href, source="배너"))
    out = dedupe(out)
    # 연금/ISA로 보이는 배너는 상세 페이지에서 기간을 읽어 본다 (실패해도 무시)
    from .base import classify
    for e in out:
        if not classify(e.title):
            continue
        try:
            text = re.sub(r"<[^>]+>", " ", http_get(e.url))
            m = _KW_PERIOD.search(text)
            if m:
                y1, m1, d1, y2, m2, d2 = (int(x) for x in m.groups())
                y1 += 2000 if y1 < 100 else 0
                y2 += 2000 if y2 < 100 else 0
                e.start, e.end = f"{y1:04d}-{m1:02d}-{d1:02d}", f"{y2:04d}-{m2:02d}-{d2:02d}"
        except Exception:
            pass
    return out


def toss(b: Browser):
    q = "토스증권 (연금 OR ISA OR IRP OR 연금저축) 이벤트 when:30d"
    rss = http_get(f"https://news.google.com/rss/search?q={quote(q)}&hl=ko&gl=KR&ceid=KR:ko")
    out, cutoff = [], today_kst() - timedelta(days=30)
    for item in ET.fromstring(rss).iter("item"):
        title = (item.findtext("title") or "").strip()
        # 토스증권이 주어인 기사만 (여러 증권사 묶음 기사 제외)
        if not re.sub(r"^\[[^\]]*\]\s*", "", title).startswith("토스증권") or "이벤트" not in title:
            continue
        try:
            pub = parsedate_to_datetime(item.findtext("pubDate")).date()
        except Exception:
            pub = None
        if pub and pub < cutoff:
            continue
        title = re.sub(r"\s+-\s+[^-]+$", "", title)  # " - 언론사" 제거
        out.append(Event(broker="토스증권", title=title, url=item.findtext("link") or "",
                         start=pub.isoformat() if pub else None, source="뉴스"))
    return out


SITES = {
    "미래에셋증권": mirae,
    "한국투자증권": kis,
    "삼성증권": samsung,
    "NH투자증권": nh,
    "KB증권": kb,
    "키움증권": kiwoom,
    "신한투자증권": shinhan,
    "토스증권": toss,
    "하나증권": hana,
    "대신증권": daishin,
}

SITE_HOME = {
    "미래에셋증권": "https://securities.miraeasset.com/hki/hki7000/r05.do",
    "한국투자증권": "https://securities.koreainvestment.com/main/customer/notice/Event.jsp?gubun=i",
    "삼성증권": "https://www.samsungpop.com/?MENU_CODE=M1231757773125",
    "NH투자증권": "https://www.nhsec.com/guestGuide/ctmList/eventIngList.action",
    "KB증권": "https://www.kbsec.com/go.able?linkcd=m06090002",
    "키움증권": "https://www.kiwoom.com/h/customer/event/VIngEventView",
    "신한투자증권": "https://www.shinhansec.com/siw/customer-center/event/giEvent1/view.do",
    "토스증권": "https://www.tossinvest.com/",
    "하나증권": "https://www.hanaw.com/corebbs5/eventIng/list/list.cmd",
    "대신증권": "https://www.daishin.com/g.ds?m=1109&p=12931&v=12831",
}
