"""데이터 수집: 지수/ETF/개별 종목 일봉, ECOS 회사채 금리.

개별 종목 일봉은 data/prices/{code}.csv 에 캐시하고, 다음 실행 때는 마지막 날짜 이후만 받아 붙인다.
"""
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import FinanceDataReader as fdr
import pandas as pd
import requests

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
PRICES = DATA / "prices"
START = "2017-01-01"


def series(symbol: str, start: str = START) -> pd.DataFrame:
    """지수(KS11 등)나 ETF 코드의 일봉."""
    df = fdr.DataReader(symbol, start)
    df.index = pd.to_datetime(df.index).normalize()
    return df


def _naver_daily(code: str, start: str) -> pd.DataFrame:
    """네이버 차트 API 일봉(수정주가). FinanceDataReader 경유 시 가끔 응답이 걸려 직접 호출한다."""
    count = int((pd.Timestamp.today() - pd.Timestamp(start)).days * 0.75) + 10
    url = f"https://fchart.stock.naver.com/sise.nhn?symbol={code}&timeframe=day&count={count}&requestType=0"
    for attempt in range(3):
        try:
            r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=(5, 15))
            r.raise_for_status()
            break
        except requests.RequestException:
            if attempt == 2:
                raise
    rows = [line.split('"')[1].split("|") for line in r.text.splitlines() if "<item data=" in line]
    df = pd.DataFrame(rows, columns=["Date", "Open", "High", "Low", "Close", "Volume"])
    df.index = pd.to_datetime(df.pop("Date"))
    df = df.astype(float)
    return df[df.index >= start]


def _update_one(code: str) -> tuple[str, pd.DataFrame | None]:
    path = PRICES / f"{code}.csv"
    old = None
    start = START
    if path.exists():
        old = pd.read_csv(path, index_col=0, parse_dates=True)
        if len(old):
            start = (old.index[-1] - pd.DateOffset(days=7)).strftime("%Y-%m-%d")
    try:
        new = _naver_daily(code, start)
    except Exception:
        return code, old
    if old is None:
        df = new
    elif len(new) == 0:
        return code, old
    else:
        df = pd.concat([old[old.index < new.index.min()], new])
    df.to_csv(path)
    return code, df


def all_stocks(workers: int = 8, log=print) -> dict[str, pd.DataFrame]:
    """KOSPI·KOSDAQ 현재 상장 보통주 전체의 일봉. (상장폐지 종목은 빠지므로 과거 구간에 생존 편향이 있다)"""
    PRICES.mkdir(parents=True, exist_ok=True)
    listing = pd.concat([fdr.StockListing("KOSPI"), fdr.StockListing("KOSDAQ")])
    # 우선주(코드 끝자리 0이 아님)·스팩 제외
    listing = listing[listing["Code"].str.endswith("0") & ~listing["Name"].str.contains("스팩")]
    codes = listing["Code"].tolist()
    out = {}
    with ThreadPoolExecutor(workers) as ex:
        futs = [ex.submit(_update_one, c) for c in codes]
        for i, f in enumerate(as_completed(futs), 1):
            code, df = f.result()
            if df is not None and len(df):
                out[code] = df
            if i % 200 == 0:
                log(f"  종목 {i}/{len(codes)}")
    return out


def ecos_credit_spread(start: str = START) -> pd.Series | None:
    """회사채 3년 AA- 금리 − 국고채 3년 금리 (%p). ECOS_API_KEY 환경변수가 없으면 None.

    BBB- − AA- 스프레드는 민평 금리 특성상 위기 때도 거의 움직이지 않아(±0.05%p) 쓰지 않는다.
    AA- − 국고채는 2020년 코로나, 2022년 레고랜드 사태 때 0.5%p → 1.8%p 수준으로 크게 벌어졌다.
    """
    key = os.environ.get("ECOS_API_KEY")
    if not key:
        return None
    s, e = start.replace("-", ""), pd.Timestamp.today().strftime("%Y%m%d")
    out = {}
    for name, item in {"AA": "010300000", "KTB": "010200000"}.items():
        url = f"https://ecos.bok.or.kr/api/StatisticSearch/{key}/json/kr/1/100000/817Y002/D/{s}/{e}/{item}"
        rows = requests.get(url, timeout=30).json()["StatisticSearch"]["row"]
        out[name] = pd.Series({pd.Timestamp(r["TIME"]): float(r["DATA_VALUE"]) for r in rows})
    return (out["AA"] - out["KTB"]).dropna().sort_index()
