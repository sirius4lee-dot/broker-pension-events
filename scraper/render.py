"""docs/index.html 생성. 데이터는 JSON으로 박아 넣고 필터/정렬은 브라우저 JS로."""
from __future__ import annotations

import json

TEMPLATE = r"""<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>연금·ISA 이벤트 모음</title>
<meta name="description" content="메이저 증권사 10곳의 연금저축·IRP·퇴직연금·ISA 이벤트를 매주 모아 보여줍니다.">
<style>
:root{--bg:#f6f7f9;--card:#fff;--ink:#14181f;--sub:#5b6472;--line:#e3e6eb;--accent:#2f6fde;--accent-soft:#e8f0fd;
--warn:#c2410c;--warn-soft:#fff1e8;--new:#0f8a5f;--new-soft:#e5f6ee;--muted-soft:#eef0f3}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){--bg:#0f1216;--card:#171b21;--ink:#e8ebf0;--sub:#9aa3b1;--line:#2a3039;
--accent:#7aa7ff;--accent-soft:#1b2a45;--warn:#ff9a62;--warn-soft:#3a2216;--new:#4fd1a0;--new-soft:#123528;--muted-soft:#222831}}
:root[data-theme="dark"]{--bg:#0f1216;--card:#171b21;--ink:#e8ebf0;--sub:#9aa3b1;--line:#2a3039;--accent:#7aa7ff;--accent-soft:#1b2a45;
--warn:#ff9a62;--warn-soft:#3a2216;--new:#4fd1a0;--new-soft:#123528;--muted-soft:#222831}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.5 -apple-system,BlinkMacSystemFont,"Apple SD Gothic Neo","Malgun Gothic",sans-serif}
.wrap{max-width:1080px;margin:0 auto;padding:28px 16px 60px}
h1{font-size:24px;margin:0 0 4px;letter-spacing:-.02em}
.meta{color:var(--sub);font-size:13px}
.stats{display:flex;gap:10px;flex-wrap:wrap;margin:18px 0 8px}
.stat{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:10px 14px;min-width:110px}
.stat b{display:block;font-size:22px;font-variant-numeric:tabular-nums}
.stat span{color:var(--sub);font-size:12px}
.filters{margin:16px 0 6px;display:grid;gap:8px}
.row{display:flex;gap:6px;flex-wrap:wrap;align-items:center}
.row .lbl{color:var(--sub);font-size:12px;width:44px;flex:none}
.chip{border:1px solid var(--line);background:var(--card);color:var(--ink);border-radius:999px;padding:5px 11px;font-size:13px;cursor:pointer}
.chip[aria-pressed="true"]{background:var(--accent);border-color:var(--accent);color:#fff}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:12px;margin-top:14px}
.card{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:14px 16px;display:flex;flex-direction:column;gap:6px;text-decoration:none;color:inherit}
.card:hover{border-color:var(--accent)}
.top{display:flex;justify-content:space-between;gap:8px;align-items:center;font-size:12px;color:var(--sub)}
.broker{font-weight:600;color:var(--ink)}
.t{font-weight:600;font-size:15.5px;line-height:1.4}
.d{color:var(--sub);font-size:13px}
.tags{display:flex;gap:6px;flex-wrap:wrap;margin-top:auto;padding-top:4px}
.tag{font-size:11.5px;padding:2px 8px;border-radius:6px;background:var(--accent-soft);color:var(--accent)}
.tag.new{background:var(--new-soft);color:var(--new);font-weight:600}
.tag.soon{background:var(--warn-soft);color:var(--warn);font-weight:600}
.tag.muted{background:var(--muted-soft);color:var(--sub)}
.period{font-variant-numeric:tabular-nums}
.empty{color:var(--sub);padding:30px 0;text-align:center}
h2{font-size:16px;margin:36px 0 10px}
table{width:100%;border-collapse:collapse;background:var(--card);border:1px solid var(--line);border-radius:12px;overflow:hidden;font-size:13.5px}
td,th{padding:8px 12px;border-bottom:1px solid var(--line);text-align:left}
th{color:var(--sub);font-weight:500;font-size:12px}
tr:last-child td{border-bottom:0}
a{color:var(--accent)}
.ok{color:var(--new)}.fail{color:var(--warn)}
.note{color:var(--sub);font-size:12.5px;margin-top:12px}
@media (max-width:520px){h1{font-size:21px}.grid{grid-template-columns:1fr}.stats{display:grid;grid-template-columns:1fr 1fr}.stat{min-width:0}td,th{padding:7px 8px}}
</style>
</head>
<body>
<div class="wrap">
  <h1>증권사 연금·ISA 이벤트</h1>
  <div class="meta">메이저 증권사 10곳 · 매주 월요일 자동 갱신 · 마지막 갱신 <span id="upd"></span></div>
  <div class="stats" id="stats"></div>
  <div class="filters">
    <div class="row" id="fKind"><span class="lbl">분류</span></div>
    <div class="row" id="fBroker"><span class="lbl">증권사</span></div>
  </div>
  <div class="grid" id="grid"></div>
  <h2>수집 현황</h2>
  <table><thead><tr><th>증권사</th><th>상태</th><th>연금·ISA</th><th>출처</th></tr></thead><tbody id="src"></tbody></table>
  <p class="note">각 증권사 공식 이벤트 페이지에서 제목에 연금·IRP·퇴직연금·ISA·절세 관련 단어가 있는 진행 중 이벤트만 모았습니다.
  키움증권은 메인 배너 기준이라 일부만 잡히고, 토스증권은 웹 이벤트 목록이 없어 보도자료(뉴스) 기준입니다.
  세부 조건은 반드시 원문에서 확인하세요.</p>
</div>
<script>
const DATA = __DATA__;
const NEW = new Set(__NEW__);
const BROKERS = Object.keys(DATA.sources);
const KINDS = ["연금저축","IRP·퇴직연금","ISA","절세계좌","연금·ISA 기타"];
const today = new Date(new Date().toLocaleString("en-US",{timeZone:"Asia/Seoul"})); today.setHours(0,0,0,0);
let kind = null, broker = null;
const $ = s => document.querySelector(s);
const esc = s => String(s ?? "").replace(/[&<>"]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
const dday = end => end ? Math.round((new Date(end+"T00:00:00") - today)/864e5) : null;
const md = s => s ? s.slice(5).replace("-","/") : "";

$("#upd").textContent = DATA.updated + " KST";
function chips(el, list, get, set){
  const mk = (label, val) => { const b = document.createElement("button"); b.className="chip"; b.textContent=label;
    b.setAttribute("aria-pressed", String(get()===val)); b.onclick=()=>{ set(get()===val?null:val); draw(); }; return b; };
  el.querySelectorAll(".chip").forEach(c=>c.remove());
  el.append(mk("전체", null), ...list.map(v=>mk(v, v)));
  el.querySelectorAll(".chip")[0].setAttribute("aria-pressed", String(get()===null));
}
function draw(){
  chips($("#fKind"), KINDS.filter(k=>DATA.events.some(e=>e.kind.includes(k))), ()=>kind, v=>kind=v);
  chips($("#fBroker"), BROKERS.filter(b=>DATA.events.some(e=>e.broker===b)), ()=>broker, v=>broker=v);
  const list = DATA.events.filter(e => (!kind || e.kind.includes(kind)) && (!broker || e.broker===broker));
  $("#grid").innerHTML = list.length ? list.map(e => {
    const d = dday(e.end);
    const tags = e.kind.split(" / ").map(k=>`<span class="tag">${esc(k)}</span>`).join("")
      + (NEW.has(e.key) ? `<span class="tag new">NEW</span>` : "")
      + (d!==null && d<=14 ? `<span class="tag soon">${d<=0?"오늘 마감":"D-"+d}</span>` : "")
      + (e.source!=="공식" ? `<span class="tag muted">${esc(e.source)} 기준</span>` : "")
      + (e.stale ? `<span class="tag muted">지난주 정보</span>` : "");
    const period = e.start||e.end ? `${md(e.start)}${e.end?" ~ "+md(e.end):""}` : "기간 미표기";
    return `<a class="card" href="${esc(e.url)}" target="_blank" rel="noopener">
      <div class="top"><span class="broker">${esc(e.broker)}</span><span class="period">${period}</span></div>
      <div class="t">${esc(e.title)}</div>${e.desc?`<div class="d">${esc(e.desc)}</div>`:""}
      <div class="tags">${tags}</div></a>`;
  }).join("") : `<div class="empty">조건에 맞는 이벤트가 없어요.</div>`;
}
const live = DATA.events.filter(e=>!e.stale);
const soon = live.filter(e=>{const d=dday(e.end);return d!==null&&d<=14}).length;
const okN = BROKERS.filter(b=>!(b in DATA.failures)).length;
$("#stats").innerHTML = [[DATA.events.length,"진행 중"],[NEW.size,"이번 주 신규"],[soon,"2주 내 마감"],[`${okN}/${BROKERS.length}`,"확인된 증권사"]]
  .map(([n,l])=>`<div class="stat"><b>${n}</b><span>${l}</span></div>`).join("");
$("#src").innerHTML = BROKERS.map(b=>{
  const fail = DATA.failures[b]; const n = DATA.events.filter(e=>e.broker===b).length;
  return `<tr><td>${esc(b)}</td><td class="${fail?"fail":"ok"}">${fail?"확인 실패":"정상"}</td><td>${n}건</td>
    <td><a href="${esc(DATA.sources[b])}" target="_blank" rel="noopener">이벤트 페이지</a></td></tr>`;}).join("");
draw();
</script>
</body>
</html>
"""


def render(state: dict, new_keys: set[str]) -> str:
    data = json.dumps(state, ensure_ascii=False).replace("</", "<\\/")
    return TEMPLATE.replace("__DATA__", data).replace("__NEW__", json.dumps(sorted(new_keys), ensure_ascii=False))
