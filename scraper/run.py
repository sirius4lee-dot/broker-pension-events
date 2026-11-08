"""주간 실행: 10개 증권사 수집 → 연금/ISA 필터 → 지난주와 비교 → 페이지/JSON 저장 → ntfy 요약.

python -m scraper.run [--dry-run] [--test] [--only 키움증권,토스증권]
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import traceback
from datetime import date, datetime, timedelta
from pathlib import Path

import requests

from .base import KST, Browser, classify, today_kst
from .render import render
from .sites import SITE_HOME, SITES

ROOT = Path(__file__).resolve().parent.parent
STATE = ROOT / "data" / "events.json"
PAGE = ROOT / "docs" / "index.html"
PAGE_URL = "https://sirius4lee-dot.github.io/broker-pension-events/"


def pension_category(e) -> str | None:
    cat = classify(f"{e.title} {e.desc}")
    if not cat and e.category == "연금/ISA":
        cat = "연금·ISA 기타"
    return cat


def collect(only: list[str] | None):
    today = today_kst().isoformat()
    results, failures, totals = {}, {}, {}
    b = Browser()
    try:
        for name, fn in SITES.items():
            if only and name not in only:
                continue
            try:
                evs = fn(b)
                if not evs and name != "토스증권":
                    raise RuntimeError("이벤트 0건 — 페이지 구조가 바뀌었을 수 있음")
                totals[name] = len(evs)
                keep = []
                for e in evs:
                    cat = pension_category(e)
                    if not cat or (e.end and e.end < today):
                        continue
                    d = e.to_dict()
                    d["kind"] = cat
                    keep.append(d)
                results[name] = keep
                print(f"[ok] {name}: 전체 {len(evs)}건 중 연금/ISA {len(keep)}건")
            except Exception as ex:
                failures[name] = f"{type(ex).__name__}: {str(ex)[:150]}"
                print(f"[FAIL] {name}: {failures[name]}")
                traceback.print_exc()
    finally:
        b.close()
    return results, failures, totals


def merge(prev: dict, results: dict, failures: dict, only):
    today = today_kst().isoformat()
    prev_events = {e["key"]: e for e in prev.get("events", [])}
    first_run = not prev_events
    events, new, ended = [], [], []
    for name in SITES:
        if name in results:
            # 이전에 한 번도 성공 못 한 증권사는 첫 수집 → 전부 '신규'로 띄우지 않음
            broker_first = first_run or name not in prev.get("totals", {})
            cur_keys = set()
            for e in results[name]:
                cur_keys.add(e["key"])
                old = prev_events.get(e["key"])
                e["first_seen"] = old["first_seen"] if old else today
                e["stale"] = False
                if not old and not broker_first:
                    new.append(e)
                events.append(e)
            ended += [p for k, p in prev_events.items()
                      if p["broker"] == name and k not in cur_keys and not p.get("stale")
                      and (not p.get("end") or p["end"] >= today)]
        else:
            # 실패했거나(--only로) 이번에 안 돌린 증권사는 지난 결과 유지
            for p in prev_events.values():
                if p["broker"] == name and (not p.get("end") or p["end"] >= today):
                    p = dict(p)
                    p["stale"] = name in failures or p.get("stale", False)
                    events.append(p)
    return events, new, ended, first_run


def summary_text(events, new, ended, failures, first_run, totals) -> tuple[str, str]:
    today = today_kst()
    title = f"증권사 연금/ISA 이벤트 주간 요약 ({today:%m/%d})"
    ok = len([n for n in SITES if n not in failures])
    lines = [f"진행 중 {len(events)}건 · {ok}/{len(SITES)}곳 확인"]

    def fmt(e):
        end = f" ~{e['end'][5:].replace('-', '/')}" if e.get("end") else ""
        return f"· {e['broker'].replace('증권', '').replace('투자', '')} {e['title']}{end}"

    if first_run:
        lines.append("\n(첫 수집이라 신규 표시는 다음 주부터)")
    elif new:
        lines.append(f"\n🆕 신규 {len(new)}건")
        lines += [fmt(e) for e in new]
    else:
        lines.append("\n🆕 신규 없음")

    soon_limit = (today + timedelta(days=14)).isoformat()
    soon = sorted([e for e in events if e.get("end") and e["end"] <= soon_limit and not e.get("stale")],
                  key=lambda e: e["end"])
    if soon:
        lines.append(f"\n⏰ 2주 내 마감 {len(soon)}건")
        lines += [fmt(e) for e in soon]
    if ended:
        lines.append(f"\n🔚 목록에서 내려감 {len(ended)}건")
        lines += [fmt(e) for e in ended[:8]]
    if failures:
        lines.append("\n⚠️ 확인 실패: " + ", ".join(failures))
    body = "\n".join(lines)
    while len(body.encode()) > 3800:
        body = body[: int(len(body) * 0.9)].rsplit("\n", 1)[0] + "\n…(이하 페이지 참고)"
    return title, body


def send_ntfy(title: str, body: str, priority: int):
    topic = os.environ.get("NTFY_TOPIC")
    if not topic:
        print("NTFY_TOPIC 없음 → 알림 생략")
        return
    # 한글 제목은 헤더로 못 보내서 JSON publish 사용
    r = requests.post("https://ntfy.sh/", json={
        "topic": topic, "title": title, "message": body, "priority": priority,
        "tags": ["chart_with_upwards_trend"], "click": PAGE_URL,
    }, timeout=30)
    r.raise_for_status()
    print("ntfy 전송 완료")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="알림·상태 저장 없이 페이지만 생성")
    ap.add_argument("--test", action="store_true", help="알림 제목에 [테스트] 표시")
    ap.add_argument("--only", default="", help="쉼표로 구분한 증권사 이름")
    a = ap.parse_args()
    only = [x.strip() for x in a.only.split(",") if x.strip()] or None

    prev = json.loads(STATE.read_text(encoding="utf-8")) if STATE.exists() else {}
    results, failures, totals = collect(only)
    events, new, ended, first_run = merge(prev, results, failures, only)
    events.sort(key=lambda e: (e.get("end") or "9999", e["broker"]))
    now = datetime.now(KST).strftime("%Y-%m-%d %H:%M")
    totals = {**prev.get("totals", {}), **totals}  # --only 실행 때도 이전 성공 기록 유지
    state = {"updated": now, "events": events, "failures": failures, "totals": totals,
             "sources": SITE_HOME}

    PAGE.parent.mkdir(parents=True, exist_ok=True)
    PAGE.write_text(render(state, new_keys={e["key"] for e in new}), encoding="utf-8")
    title, body = summary_text(events, new, ended, failures, first_run, totals)
    if a.test:
        title = "[테스트] " + title
    print("\n" + title + "\n" + body)
    if a.dry_run:
        return
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(state, ensure_ascii=False, indent=1), encoding="utf-8")
    send_ntfy(title, body, priority=4 if new else 3)
    if len(failures) >= 5:
        sys.exit(1)  # 절반 이상 실패하면 Actions에서도 빨간불


if __name__ == "__main__":
    main()
