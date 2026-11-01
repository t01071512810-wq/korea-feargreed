"""지표 원시값 계산과 0~100 점수 환산.

각 지표는 "값이 클수록 탐욕"이 되도록 방향을 맞춘 뒤, 최근 WINDOW 거래일 안에서의 백분위를 점수로 쓴다.
"""
import numpy as np
import pandas as pd

WINDOW = 252  # 점수 환산에 쓰는 과거 구간(약 1년)
MIN_PERIODS = 120

LABELS = [(25, "극단적 공포"), (45, "공포"), (55, "중립"), (75, "탐욕"), (101, "극단적 탐욕")]


def label(score: float) -> str:
    return next(name for cut, name in LABELS if score < cut)


def percentile_score(x: pd.Series) -> pd.Series:
    return x.rolling(WINDOW, min_periods=MIN_PERIODS).rank(pct=True) * 100


def momentum(kospi: pd.Series) -> pd.Series:
    """KOSPI가 125일 이동평균보다 몇 % 위/아래인가."""
    return (kospi / kospi.rolling(125).mean() - 1) * 100


def high_low(high: pd.DataFrame, low: pd.DataFrame, close: pd.DataFrame) -> pd.Series:
    """(52주 신고가 종목 수 − 신저가 종목 수) / 거래 종목 수, %."""
    hi52 = high.rolling(252, min_periods=240).max()
    lo52 = low.rolling(252, min_periods=240).min()
    valid = hi52.notna() & close.notna()
    n_hi = ((high >= hi52) & valid).sum(axis=1)
    n_lo = ((low <= lo52) & valid).sum(axis=1)
    return (n_hi - n_lo) / valid.sum(axis=1).replace(0, np.nan) * 100


def breadth(close: pd.DataFrame, volume: pd.DataFrame) -> pd.Series:
    """McClellan Volume Summation Index (상승/하락 종목 거래량 비율 기반)."""
    chg = close.diff()
    adv = volume.where(chg > 0).sum(axis=1)
    dec = volume.where(chg < 0).sum(axis=1)
    ratio = (adv - dec) / (adv + dec).replace(0, np.nan) * 1000
    osc = ratio.ewm(span=19, adjust=False).mean() - ratio.ewm(span=39, adjust=False).mean()
    return osc.cumsum()


def volatility(kospi: pd.Series) -> pd.Series:
    """KOSPI 20일 실현변동성이 50일 평균보다 몇 % 높은가. (VKOSPI 대용, 높을수록 공포)"""
    vol = np.log(kospi).diff().rolling(20).std() * np.sqrt(252) * 100
    return (vol / vol.rolling(50).mean() - 1) * 100


def safe_haven(kospi: pd.Series, bond: pd.Series) -> pd.Series:
    """KOSPI 20일 수익률 − 국고채 ETF 20일 수익률, %p. (클수록 위험자산 선호)"""
    return (kospi.pct_change(20) - bond.pct_change(20)) * 100


def inverse_demand(inverse_value: pd.Series, leverage_value: pd.Series) -> pd.Series:
    """인버스 ETF 거래대금 / 레버리지 ETF 거래대금 (5일 합계). 풋/콜 비율 대용, 높을수록 공포."""
    return inverse_value.rolling(5).sum() / leverage_value.rolling(5).sum()


# key, 이름, 설명, 단위, 탐욕 방향(+1: 값이 클수록 탐욕, -1: 작을수록 탐욕)
SPECS = {
    "momentum": ("시장 모멘텀", "KOSPI와 125일 이동평균의 괴리율", "%", 1),
    "high_low": ("주가 강도", "52주 신고가 − 신저가 종목 비율 (KOSPI+KOSDAQ)", "%", 1),
    "breadth": ("시장 폭", "McClellan 거래량 합산지수 (상승·하락 종목 거래량)", "", 1),
    "volatility": ("시장 변동성", "KOSPI 20일 실현변동성의 50일 평균 대비 수준", "%", -1),
    "inverse": ("하락 베팅 수요", "인버스 ÷ 레버리지 ETF 거래대금 5일 합계 (풋/콜 비율 대용)", "배", -1),
    "safe_haven": ("안전자산 수요", "KOSPI − 국고채10년 ETF 20일 수익률 차", "%p", 1),
    "credit": ("신용 스프레드", "회사채 3년 AA− 금리 − 국고채 3년 금리 (ECOS)", "%p", -1),
}


def score(raw: pd.DataFrame) -> pd.DataFrame:
    out = pd.DataFrame(index=raw.index)
    for key in raw.columns:
        direction = SPECS[key][3]
        out[key] = percentile_score(raw[key] * direction)
    return out
