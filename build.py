"""데이터를 받아 지수를 계산하고 docs/data.json 을 만든다.

    python build.py            # 전 종목 캐시 갱신 + 계산

.env 파일에 ECOS_API_KEY 가 있으면 신용 스프레드 지표도 포함한다.
"""
import json
import os
import time
from pathlib import Path

import pandas as pd

from kfg import fetch
from kfg import indicators as ind

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "docs" / "data.json"
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


def main():
    load_env()
    t0 = time.time()
    print("지수·ETF 수집")
    kospi = fetch.series("KS11")["Close"]
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

    raw = pd.DataFrame({
        "momentum": ind.momentum(kospi),
        "high_low": ind.high_low(wide["High"], wide["Low"], wide["Close"]),
        "breadth": ind.breadth(wide["Close"], wide["Volume"]),
        "volatility": ind.volatility(kospi),
        "inverse": ind.inverse_demand(inverse, leverage),
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
    write_json(kospi.loc[total.index], raw, scores, total)
    print(f"완료: {total.index[-1].date()} 점수 {total.iloc[-1]:.0f} ({ind.label(total.iloc[-1])}), {time.time() - t0:.0f}초")


def write_json(kospi, raw, scores, total):
    last = total.index[-1]

    def ago(days):
        return round(float(total.loc[: last - pd.DateOffset(days=days)].iloc[-1]), 1)

    data = {
        "updated": last.strftime("%Y-%m-%d"),
        "score": round(float(total.iloc[-1]), 1),
        "label": ind.label(total.iloc[-1]),
        "kospi": round(float(kospi.iloc[-1]), 2),
        "compare": {
            "전일": round(float(total.iloc[-2]), 1),
            "1주 전": ago(7),
            "1개월 전": ago(30),
            "1년 전": ago(365),
        },
        "indicators": [
            {
                "key": k,
                "name": ind.SPECS[k][0],
                "desc": ind.SPECS[k][1],
                "unit": ind.SPECS[k][2],
                "raw": round(float(raw[k].iloc[-1]), 2),
                "score": round(float(scores[k].iloc[-1]), 1),
                "label": ind.label(scores[k].iloc[-1]),
                "history": [round(float(v), 1) for v in scores[k].iloc[-252:]],
            }
            for k in scores.columns
        ],
        "history": {
            "dates": [d.strftime("%Y-%m-%d") for d in total.index],
            "score": [round(float(v), 1) for v in total],
            "kospi": [round(float(v), 2) for v in kospi],
        },
    }
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    main()
