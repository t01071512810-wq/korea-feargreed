"""KRX OPEN API: VKOSPI(코스피 200 변동성지수)와 코스피200 옵션 풋/콜 거래량·거래대금.

API가 하루치씩만 조회되므로 날짜별 요약을 data/krx_daily.csv 에 쌓아 두고(저장소에 커밋),
다음 실행부터는 아직 없는 날짜만 받는다. KRX_API_KEY 환경변수가 없으면 아무것도 하지 않는다.
"""
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parent.parent
CSV = ROOT / "data" / "krx_daily.csv"
BASE = "https://data-dbg.krx.co.kr/svc/apis/"
VKOSPI_NAME = "코스피 200 변동성지수"
# 시장 대표 옵션(위클리 포함). 미니·코스닥150 옵션은 뺀다
KOSPI200_OPTIONS = {"코스피200 옵션", "코스피200 위클리(월) 옵션", "코스피200 위클리(목) 옵션"}
VKOSPI_START = "2013-01-01"  # 750일(약 3년) 평균을 2017년부터 쓰려면 3년 넘게 앞서 필요
OPTION_START = "2017-01-01"


def _get(path: str, day: pd.Timestamp, key: str) -> list[dict] | None:
    """하루치 응답 행. 실패하면 None, 아직 발표 전이면 빈 리스트."""
    for _ in range(3):
        try:
            r = requests.get(BASE + path, params={"basDd": day.strftime("%Y%m%d")},
                             headers={"AUTH_KEY": key}, timeout=(5, 60))
            if r.status_code == 200:
                return r.json().get("OutBlock_1", [])
        except (requests.RequestException, ValueError):
            pass
    return None


def _vkospi(day, key):
    rows = _get("idx/drvprod_dd_trd", day, key)
    if not rows:
        return None
    row = next((r for r in rows if r["IDX_NM"] == VKOSPI_NAME), None)
    return float(row["CLSPRC_IDX"]) if row and row["CLSPRC_IDX"] else None


def _put_call(day, key):
    rows = _get("drv/opt_bydd_trd", day, key)
    if not rows:
        return None
    vol = {"PUT": 0, "CALL": 0}
    val = {"PUT": 0, "CALL": 0}
    for r in rows:
        # 야간 거래분은 따로 들어오므로 정규장만 센다
        if r["PROD_NM"] in KOSPI200_OPTIONS and "(야간)" not in r["ISU_NM"]:
            vol[r["RGHT_TP_NM"]] += int(r["ACC_TRDVOL"] or 0)
            val[r["RGHT_TP_NM"]] += int(r["ACC_TRDVAL"] or 0)
    return (vol["PUT"], vol["CALL"], val["PUT"], val["CALL"]) if val["CALL"] else None


COLUMNS = ["vkospi", "put_vol", "call_vol", "put_val", "call_val"]


def load() -> pd.DataFrame:
    if CSV.exists():
        return pd.read_csv(CSV, index_col="date", parse_dates=True).reindex(columns=COLUMNS).astype(float)
    return pd.DataFrame(columns=COLUMNS, index=pd.DatetimeIndex([], name="date"))


def update(trading_days: pd.DatetimeIndex, workers: int = 4, log=print) -> pd.DataFrame | None:
    """거래일 중 아직 없는 날짜를 받아 CSV에 더하고 전체를 돌려준다. 키가 없으면 None."""
    key = os.environ.get("KRX_API_KEY")
    if not key:
        return None
    df = load()

    def missing(col, start):
        days = trading_days[trading_days >= start]
        have = df[col].dropna().index if col in df else pd.DatetimeIndex([])
        return [d for d in days if d not in have]

    jobs = [("vkospi", d) for d in missing("vkospi", VKOSPI_START)] + \
           [("put_call", d) for d in missing("put_val", OPTION_START)]
    if jobs:
        log(f"  KRX {len(jobs)}건 조회")
    fn = {"vkospi": _vkospi, "put_call": _put_call}
    CSV.parent.mkdir(exist_ok=True)
    # 처음 백필은 수천 건이라 200건마다 저장해 중간에 끊겨도 이어 받을 수 있게 한다
    for i in range(0, len(jobs), 200):
        chunk = jobs[i:i + 200]
        with ThreadPoolExecutor(workers) as ex:
            results = list(ex.map(lambda j: (j, fn[j[0]](j[1], key)), chunk))
        for (kind, day), value in results:
            if value is None:
                continue  # 아직 발표 전이거나 실패: 다음 실행에서 다시 받는다
            if kind == "vkospi":
                df.loc[day, "vkospi"] = value
            else:
                for col, x in zip(COLUMNS[1:], value):
                    df.loc[day, col] = x
        df = df.sort_index()
        df.index.name = "date"
        df.to_csv(CSV)
        if len(jobs) > 200:
            log(f"  KRX {min(i + 200, len(jobs))}/{len(jobs)}")
    return df
