# 증권사 연금·ISA 이벤트 주간 요약

메이저 증권사 10곳(미래에셋·한국투자·삼성·NH·KB·키움·신한·토스·하나·대신)의 연금저축·IRP·퇴직연금·ISA 이벤트를
매주 월요일 08:17 KST에 수집해서

- 페이지: https://sirius4lee-dot.github.io/broker-pension-events/
- ntfy 주간 요약 (신규 / 2주 내 마감 / 내려간 이벤트 / 확인 실패)

로 알려줍니다.

```
pip install -r requirements.txt && python -m playwright install chromium
python -m scraper.run --dry-run          # 알림/상태 저장 없이 docs/index.html만 생성
python -m scraper.run --only KB증권,하나증권 --dry-run
```

수집 방식은 `scraper/sites.py` 상단 주석 참고. 사이트 개편으로 0건이 나오면 "확인 실패"로 표시됩니다.
