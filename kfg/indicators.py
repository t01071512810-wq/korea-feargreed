"""지표 원시값 계산과 0~100 점수 환산.

각 지표는 "값이 클수록 탐욕"이 되도록 방향을 맞춘 뒤, 최근 WINDOW 거래일 안에서의 백분위를 점수로 쓴다.
"""
import numpy as np
import pandas as pd

WINDOW = 252  # 점수 환산에 쓰는 과거 구간(약 1년)
MIN_PERIODS = 120
# 지표별로 다른 구간을 쓰는 경우. 시장 변동성은 "장기 평균 대비 지금"을 보려고 약 3년으로 순위를 매긴다
WINDOWS = {"vkospi": (750, 250), "volatility": (750, 250)}
LONG_VOL_DAYS = 750  # 약 3년

LABELS = [(25, "극단적 공포"), (45, "공포"), (55, "중립"), (75, "탐욕"), (101, "극단적 탐욕")]


def label(score: float) -> str:
    return next(name for cut, name in LABELS if score < cut)


def percentile_score(x: pd.Series, window: int = WINDOW, min_periods: int = MIN_PERIODS) -> pd.Series:
    return x.rolling(window, min_periods=min_periods).rank(pct=True) * 100


def momentum(kospi: pd.Series) -> pd.Series:
    """KOSPI가 125일 이동평균보다 몇 % 위/아래인가."""
    return (kospi / kospi.rolling(125).mean() - 1) * 100


def high_low_counts(high: pd.DataFrame, low: pd.DataFrame, close: pd.DataFrame) -> pd.DataFrame:
    """날짜별 52주 신고가 종목 수(hi), 신저가 종목 수(lo), 비교 가능한 종목 수(n)."""
    hi52 = high.rolling(252, min_periods=240).max()
    lo52 = low.rolling(252, min_periods=240).min()
    valid = hi52.notna() & close.notna()
    return pd.DataFrame({
        "hi": ((high >= hi52) & valid).sum(axis=1),
        "lo": ((low <= lo52) & valid).sum(axis=1),
        "n": valid.sum(axis=1),
    })


def high_low(counts: pd.DataFrame) -> pd.Series:
    """(52주 신고가 종목 수 − 신저가 종목 수) / 비교 가능한 종목 수, %."""
    return (counts["hi"] - counts["lo"]) / counts["n"].replace(0, np.nan) * 100


def breadth(close: pd.DataFrame, volume: pd.DataFrame) -> pd.Series:
    """McClellan Volume Summation Index (상승/하락 종목 거래량 비율 기반)."""
    chg = close.diff()
    adv = volume.where(chg > 0).sum(axis=1)
    dec = volume.where(chg < 0).sum(axis=1)
    ratio = (adv - dec) / (adv + dec).replace(0, np.nan) * 1000
    osc = ratio.ewm(span=19, adjust=False).mean() - ratio.ewm(span=39, adjust=False).mean()
    return osc.cumsum()


def down_volume_share(close: pd.DataFrame, volume: pd.DataFrame, days: int = 10) -> pd.Series:
    """최근 days일 동안 상승·하락 종목 거래량 합계 중 하락 종목 거래량의 비중, %."""
    chg = close.diff()
    adv = volume.where(chg > 0).sum(axis=1).rolling(days).sum()
    dec = volume.where(chg < 0).sum(axis=1).rolling(days).sum()
    return dec / (adv + dec).replace(0, np.nan) * 100


def volatility(kospi: pd.Series) -> pd.Series:
    """KOSPI 20일 실현변동성이 750일(약 3년) 평균보다 몇 % 높은가. (VKOSPI 대용, 높을수록 공포)"""
    vol = np.log(kospi).diff().rolling(20).std() * np.sqrt(252) * 100
    return (vol / vol.rolling(LONG_VOL_DAYS).mean() - 1) * 100


def vkospi_level(vkospi: pd.Series) -> pd.Series:
    """VKOSPI가 750일(약 3년) 평균보다 몇 % 높은가. (높을수록 공포)"""
    return (vkospi / vkospi.rolling(LONG_VOL_DAYS, min_periods=LONG_VOL_DAYS).mean() - 1) * 100


def put_call(put_val: pd.Series, call_val: pd.Series) -> pd.Series:
    """코스피200 옵션 풋 거래대금 / 콜 거래대금 (5일 합계). 높을수록 공포.
    거래량으로 세면 폭락 때 싸진 콜옵션 거래가 폭증해 오히려 비율이 내려가므로 거래대금을 쓴다."""
    return put_val.rolling(5).sum() / call_val.rolling(5).sum()


def safe_haven(kospi: pd.Series, bond: pd.Series) -> pd.Series:
    """KOSPI 20일 수익률 − 국고채 ETF 20일 수익률, %p. (클수록 위험자산 선호)"""
    return (kospi.pct_change(20) - bond.pct_change(20)) * 100


def inverse_demand(inverse_value: pd.Series, leverage_value: pd.Series) -> pd.Series:
    """인버스 ETF 거래대금 / 레버리지 ETF 거래대금 (5일 합계). 풋/콜 비율 대용, 높을수록 공포."""
    return inverse_value.rolling(5).sum() / leverage_value.rolling(5).sum()


# key, 이름, 설명, 단위, 탐욕 방향(+1: 값이 클수록 탐욕, -1: 작을수록 탐욕)
# vkospi·put_call 은 KRX OPEN API 데이터, volatility·inverse 는 KRX 데이터가 없을 때 쓰는 대체 지표
SPECS = {
    "vkospi": ("시장 변동성", "VKOSPI(코스피200 변동성지수)의 750일(약 3년) 평균 대비 수준", "%", -1),
    "put_call": ("풋/콜 비율", "코스피200 옵션 풋 ÷ 콜 거래대금 5일 합계", "배", -1),
    "momentum": ("시장 모멘텀", "KOSPI와 125일 이동평균의 괴리율", "%", 1),
    "high_low": ("주가 강도", "52주 신고가 − 신저가 종목 비율 (KOSPI+KOSDAQ)", "%", 1),
    "breadth": ("시장 폭", "McClellan 거래량 합산지수 (상승·하락 종목 거래량)", "", 1),
    "volatility": ("시장 변동성", "KOSPI 20일 실현변동성의 750일(약 3년) 평균 대비 수준", "%", -1),
    "inverse": ("하락 베팅 수요", "인버스 ÷ 레버리지 ETF 거래대금 5일 합계 (풋/콜 비율 대용)", "배", -1),
    "safe_haven": ("안전자산 수요", "KOSPI − 국고채10년 ETF 20일 수익률 차", "%p", 1),
    "credit": ("신용 스프레드", "회사채 3년 AA− 금리 − 국고채 3년 금리 (ECOS)", "%p", -1),
}


def score(raw: pd.DataFrame) -> pd.DataFrame:
    out = pd.DataFrame(index=raw.index)
    for key in raw.columns:
        direction = SPECS[key][3]
        out[key] = percentile_score(raw[key] * direction, *WINDOWS.get(key, (WINDOW, MIN_PERIODS)))
    return out


MOODS = {
    "극단적 공포": "시장 전반에 두려움이 크게 퍼져 있어요",
    "공포": "투자자들이 조심스러운 분위기예요",
    "중립": "두려움과 기대가 균형을 이루고 있어요",
    "탐욕": "투자자들이 낙관적인 분위기예요",
    "극단적 탐욕": "시장이 과열에 가까울 만큼 들떠 있어요",
}


def _more_less(v: float, more: str = "높음", less: str = "낮음") -> str:
    return more if v >= 0 else less


def plain_text(key: str, v: float, ctx: dict) -> str:
    """지표의 오늘 원시값을 처음 보는 사람도 읽을 수 있는 한 줄로."""
    text = _plain_text(key, v, ctx)
    # KRX는 그날 데이터를 저녁~다음 날 아침에 공개하므로, 아직이면 전날 값임을 밝힌다
    if key in ("vkospi", "put_call") and ctx.get("krx_stale"):
        text += " · 전일 기준"
    return text


def _plain_text(key: str, v: float, ctx: dict) -> str:
    if key == "momentum":
        return f"KOSPI가 125일 평균보다 {abs(v):.1f}% {_more_less(v)}"
    if key == "high_low":
        return f"1년 중 최고가 경신 {ctx['hi']:,}개 · 최저가 경신 {ctx['lo']:,}개 종목"
    if key == "breadth":
        # 합산지수는 몇 주간 쌓인 흐름이라 최근 10일 비중과 방향이 다를 수 있어 둘 다 보여준다
        down = ctx["down_share"]
        trend = "상승" if ctx["breadth_above_avg"] else "하락"
        return f"최근 10일 거래량 상승 {100 - down:.0f}% · 하락 {down:.0f}%, 누적 흐름은 {trend} 우세"
    if key == "volatility":
        return f"주가 출렁임이 약 3년 평균의 {1 + v / 100:.1f}배"
    if key == "vkospi":
        return f"VKOSPI {ctx['vkospi']:.1f} · 약 3년 평균의 {1 + v / 100:.1f}배"
    if key == "put_call":
        return f"하락 대비(풋)에 상승 기대(콜)의 {v:.2f}배 돈이 오감 (1년 평균 {ctx['pc_avg']:.2f}배)"
    if key == "inverse":
        return f"하락에 거는 ETF 거래가 상승에 거는 ETF의 {v:.2f}배"
    if key == "safe_haven":
        return f"최근 20일 주식 수익률이 국채보다 {abs(v):.1f}%p {_more_less(v)}"
    if key == "credit":
        return f"우량 회사채 금리가 국채보다 {v:.2f}%p 높음 (1년 평균 {ctx['credit_avg']:.2f}%p)"
    raise KeyError(key)


def summary(labels: list[str]) -> str:
    """'7개 지표 중 6개가 극단적 공포' 형식의 한 줄 요약. 같은 수면 더 극단적인 쪽을 고른다."""
    order = [name for _, name in LABELS]
    counts = {name: labels.count(name) for name in order}
    top = max(order, key=lambda name: (counts[name], abs(order.index(name) - 2)))
    if counts[top] == len(labels):
        return f"{len(labels)}개 지표 모두 {top}"
    return f"{len(labels)}개 지표 중 {counts[top]}개가 {top}"
