"""데이터를 받아 지수를 계산하고 docs/ 아래 결과물을 만든다.

    python build.py            # 전 종목 캐시 갱신 + 계산

만드는 파일: docs/data.json(페이지 데이터), docs/og.png(링크 미리보기 이미지),
docs/index.html 의 미리보기용 메타 태그(오늘 점수·상태).
.env 파일에 ECOS_API_KEY 가 있으면 신용 스프레드 지표도 포함한다.
"""
import json
import os
import re
import time
from datetime import datetime, timedelta, timezone
from html import escape
from pathlib import Path

import pandas as pd

from kfg import fetch, krx, og
from kfg import indicators as ind

ROOT = Path(__file__).resolve().parent
DOCS = ROOT / "docs"
SITE_URL = os.environ.get("SITE_URL", "https://korea-feargreed.vercel.app")
KST = timezone(timedelta(hours=9))
BOND_ETF = "148070"  # KOSEF 국고채10년
INVERSE_ETFS = ["114800", "252670"]  # KODEX 인버스, KODEX 200선물인버스2X
LEVERAGE_ETF = "122630"  # KODEX 레버리지


def load_env(path=ROOT / ".env"):
    """KEY=VALUE 형식의 .env 를 읽어 환경변수에 넣는다. 이미 설정된 환경변수(GitHub Secrets 등)가 우선."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        key, sep, value = line.partition("=")
        if sep and not key.strip().startswith("#") and value.strip():
            os.environ.setdefault(key.strip(), value.strip().strip("\"'"))


def market_closed_only(s: pd.Series) -> pd.Series:
    """장중(15:40 KST 이전)에 실행되면 오늘의 미완성 일봉을 빼고, 마감된 날까지만 남긴다.
    모든 지표가 이 날짜축(kospi.index)에 맞춰지므로 여기서 한 번만 자르면 된다."""
    now = datetime.now(KST)
    today = pd.Timestamp(now.date())
    if len(s) and s.index[-1] >= today and (now.hour, now.minute) < (15, 40):
        return s[s.index < today]
    return s


def main():
    load_env()
    t0 = time.time()
    print("지수·ETF 수집")
    # 시장 변동성의 750일(약 3년) 평균을 2017년부터 쓰려고 KOSPI만 더 일찍부터 받는다(종목 데이터는 2017년부터)
    kospi = market_closed_only(fetch.series("KS11", "2012-01-01")["Close"])
    bond = fetch.series(BOND_ETF)["Close"].reindex(kospi.index).ffill()

    def traded_value(code):
        df = fetch.series(code)
        return (df["Close"] * df["Volume"]).reindex(kospi.index).fillna(0)

    inverse = sum(traded_value(c) for c in INVERSE_ETFS)
    leverage = traded_value(LEVERAGE_ETF)

    print("개별 종목 수집")
    stocks = fetch.all_stocks()
    print(f"  {len(stocks)}개 종목")
    days = kospi.index
    wide = {f: pd.DataFrame({c: df[f] for c, df in stocks.items()}).reindex(days)
            for f in ["High", "Low", "Close", "Volume"]}
    counts = ind.high_low_counts(wide["High"], wide["Low"], wide["Close"])

    # VKOSPI·풋/콜은 KRX OPEN API에서. KRX는 그날 데이터를 저녁~다음 날 아침에 공개하므로
    # 오후 실행에서는 전날 값을 최대 3거래일까지만 이어 쓰고, 키가 없으면 대체 지표를 쓴다
    print("KRX 수집")
    krx_df = krx.update(days)
    if krx_df is not None and krx_df["vkospi"].notna().any() and krx_df["put_val"].notna().any():
        vk = krx_df["vkospi"].dropna()
        pcd = krx_df[["put_val", "call_val"]].dropna()
        vol_ind = {
            "vkospi": ind.vkospi_level(vk).reindex(days).ffill(limit=3),
            "put_call": ind.put_call(pcd["put_val"], pcd["call_val"]).reindex(days).ffill(limit=3),
        }
        vkospi_now = float(vk.reindex(days).ffill(limit=3).iloc[-1])
        krx_stale = vk.index[-1] < days[-1]
    else:
        print("  KRX_API_KEY 없음: 실현변동성·인버스 ETF 대체 지표 사용")
        vol_ind = {"volatility": ind.volatility(kospi), "inverse": ind.inverse_demand(inverse, leverage)}
        vkospi_now = None
        krx_stale = False

    raw = pd.DataFrame({
        "momentum": ind.momentum(kospi),
        "high_low": ind.high_low(counts),
        "breadth": ind.breadth(wide["Close"], wide["Volume"]),
        **vol_ind,
        "safe_haven": ind.safe_haven(kospi, bond),
    })
    spread = fetch.ecos_credit_spread()
    if spread is not None:
        raw["credit"] = spread.reindex(days).ffill()
    else:
        print("  ECOS_API_KEY 없음: 신용 스프레드 지표 제외")

    scores = ind.score(raw)
    total = scores.mean(axis=1, skipna=False).dropna()
    scores, raw = scores.loc[total.index], raw.loc[total.index]
    last = total.index[-1]
    ctx = {
        "hi": int(counts.loc[last, "hi"]),
        "lo": int(counts.loc[last, "lo"]),
        "down_share": float(ind.down_volume_share(wide["Close"], wide["Volume"]).loc[last]),
        "breadth_above_avg": bool(raw["breadth"].iloc[-1] >= raw["breadth"].iloc[-252:].mean()),
        "credit_avg": float(raw["credit"].iloc[-252:].mean()) if "credit" in raw else None,
        "vkospi": vkospi_now,
        "krx_stale": krx_stale,
        "pc_avg": float(raw["put_call"].iloc[-252:].mean()) if "put_call" in raw else None,
    }
    data = make_data(kospi.loc[total.index], raw, scores, total, ctx)
    (DOCS / "data.json").write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    og.render_card(DOCS / "og.png", data["score"], data["label"], data["summary"], data["updated"])
    update_meta(DOCS / "index.html", data)
    print(f"완료: {last.date()} 점수 {total.iloc[-1]:.0f} ({ind.label(total.iloc[-1])}), {data['summary']}, {time.time() - t0:.0f}초")


def make_data(kospi, raw, scores, total, ctx):
    last = total.index[-1]

    def ago(days):
        return round(float(total.loc[: last - pd.DateOffset(days=days)].iloc[-1]), 1)

    indicators = [
        {
            "key": k,
            "name": ind.SPECS[k][0],
            "desc": ind.SPECS[k][1],
            "unit": ind.SPECS[k][2],
            "raw": round(float(raw[k].iloc[-1]), 2),
            "text": ind.plain_text(k, float(raw[k].iloc[-1]), ctx),
            "score": round(float(scores[k].iloc[-1]), 1),
            "label": ind.label(scores[k].iloc[-1]),
            "rank": ind.rank_text(k, float(scores[k].iloc[-1])),
            "history": [round(float(v), 1) for v in scores[k].iloc[-252:]],
            "raw_history": [round(float(v), 3) for v in raw[k].iloc[-252:]],
        }
        for k in scores.columns
    ]
    label = ind.label(total.iloc[-1])
    return {
        "updated": last.strftime("%Y-%m-%d"),
        "generated_at": datetime.now(KST).strftime("%Y-%m-%d %H:%M"),
        "score": round(float(total.iloc[-1]), 1),
        "label": label,
        "mood": ind.MOODS[label],
        "summary": ind.summary([i["label"] for i in indicators]),
        "kospi": round(float(kospi.iloc[-1]), 2),
        "compare": {
            "전일": round(float(total.iloc[-2]), 1),
            "1주 전": ago(7),
            "1개월 전": ago(30),
            "1년 전": ago(365),
        },
        "indicators": indicators,
        "history": {
            "dates": [d.strftime("%Y-%m-%d") for d in total.index],
            "score": [round(float(v), 1) for v in total],
            "kospi": [round(float(v), 2) for v in kospi],
        },
    }


def update_meta(path: Path, data: dict):
    """링크 미리보기(카카오톡·X 등)가 읽는 메타 태그에 오늘 점수와 상태를 넣는다."""
    title = f"한국 공포·탐욕 지수 {data['score']:.0f}점 · {data['label']}"
    desc = f"{data['updated']} 장 마감 기준 · {data['summary']}. {data['mood']}."
    # 카카오톡은 이미지 주소별로 미리보기를 캐시하므로 날짜를 붙여 매일 새 이미지로 인식시킨다
    image = f"{SITE_URL}/og.png?v={data['updated'].replace('-', '')}"
    values = {
        "og:title": title, "og:description": desc, "og:image": image, "og:url": f"{SITE_URL}/",
        "twitter:title": title, "twitter:description": desc, "twitter:image": image,
        "description": desc,
    }
    html = path.read_text(encoding="utf-8")
    for key, value in values.items():
        pattern = rf'(<meta (?:property|name)="{re.escape(key)}" content=")[^"]*(")'
        html, n = re.subn(pattern, lambda m: m.group(1) + escape(value) + m.group(2), html)
        if n != 1:
            raise ValueError(f"index.html 에서 메타 태그 {key} 를 찾지 못했습니다")
    path.write_text(html, encoding="utf-8")


if __name__ == "__main__":
    main()
