"""링크 미리보기 이미지(og.png)와 아이콘 PNG 생성.

    python -m kfg.og     # 아이콘(favicon-32.png, apple-touch-icon.png)만 다시 만들기

글꼴은 assets/ 의 Noto Sans KR(OFL) 에서 ASCII + 자주 쓰는 한글 2,350자만 남긴 것이다.
"""
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "assets"
SS = 2  # 안티에일리어싱용 2배 그리기

CANVAS = (11, 14, 17)        # #0b0e11
CARD = (30, 35, 41)          # #1e2329
PRIMARY = (252, 213, 53)     # #fcd535
ON_DARK = (255, 255, 255)
BODY = (234, 236, 239)       # #eaecef
MUTED = (112, 122, 138)      # #707a8a
MUTED_STRONG = (146, 154, 165)
BANDS = [  # (상한, 이름, 색) — docs/index.html 의 --b0..--b4 와 같은 색
    (25, "극단적 공포", (246, 70, 93)),
    (45, "공포", (156, 58, 72)),
    (55, "중립", (71, 77, 87)),
    (75, "탐욕", (23, 137, 92)),
    (100, "극단적 탐욕", (14, 203, 129)),
]


def _font(weight: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(ASSETS / f"NotoSansKR-{weight}.ttf"), size * SS)


def _mix(c, bg, a):
    return tuple(round(x * a + y * (1 - a)) for x, y in zip(c, bg))


def _band(score):
    return next(b for b in BANDS if score < b[0] or b[0] == 100)


def _gauge(draw, cx, cy, r, width, score, bg, needle=True):
    """반원 게이지. 오늘 점수가 속한 구간만 진하게, 나머지는 배경과 섞어 흐리게."""
    import math
    lo, gap = 0, 1.4
    active = _band(score)
    for hi, _, color in BANDS:
        a0, a1 = 180 + lo * 1.8 + gap / 2, 180 + hi * 1.8 - gap / 2
        fill = color if (hi, color) == (active[0], active[2]) else _mix(color, bg, 0.4)
        draw.arc([cx - r, cy - r, cx + r, cy + r], a0, a1, fill=fill, width=width)
        lo = hi
    if not needle:
        return
    ang = math.radians(180 + score * 1.8)
    nr = r - width - 18 * SS
    nx, ny = cx + nr * math.cos(ang), cy + nr * math.sin(ang)
    w = 14 * SS
    draw.line([cx, cy, nx, ny], fill=PRIMARY, width=w)
    draw.ellipse([nx - w / 2, ny - w / 2, nx + w / 2, ny + w / 2], fill=PRIMARY)
    draw.ellipse([cx - 24 * SS, cy - 24 * SS, cx + 24 * SS, cy + 24 * SS], fill=PRIMARY)
    draw.ellipse([cx - 9 * SS, cy - 9 * SS, cx + 9 * SS, cy + 9 * SS], fill=bg)


def render_card(path: Path, score: float, label: str, summary: str, date: str):
    """1200×630 미리보기 카드: 왼쪽 게이지, 오른쪽 큰 점수·상태·요약."""
    W, H = 1200 * SS, 630 * SS
    img = Image.new("RGB", (W, H), CANVAS)
    d = ImageDraw.Draw(img)
    s = lambda v: v * SS  # noqa: E731

    d.text((s(64), s(52)), "K-Fear & Greed", font=_font("Bold", 30), fill=PRIMARY, anchor="lt")
    d.rounded_rectangle([s(40), s(120), s(600), s(590)], radius=s(24), fill=CARD)
    _gauge(d, s(320), s(470), s(230), s(50), score, CARD)
    d.text((s(115), s(515)), "공포", font=_font("Medium", 26), fill=MUTED_STRONG, anchor="mt")
    d.text((s(525), s(515)), "탐욕", font=_font("Medium", 26), fill=MUTED_STRONG, anchor="mt")

    x = s(650)
    d.text((x, s(150)), "한국 공포·탐욕 지수", font=_font("Medium", 36), fill=MUTED_STRONG, anchor="ls")
    d.text((x - s(8), s(370)), f"{score:.0f}", font=_font("Bold", 220), fill=PRIMARY, anchor="ls")
    color = _band(score)[2]
    d.ellipse([x, s(420), x + s(30), s(450)], fill=color)
    d.text((x + s(46), s(452)), label, font=_font("Bold", 64), fill=ON_DARK, anchor="ls")
    d.text((x, s(520)), summary, font=_font("Medium", 32), fill=BODY, anchor="ls")
    d.text((x, s(566)), f"{date} 장 마감 기준", font=_font("Medium", 26), fill=MUTED, anchor="ls")

    img.resize((1200, 630), Image.LANCZOS).save(path, optimize=True)


def render_icon(path: Path, size: int, score: float = 72):
    """게이지 모양 아이콘 (둥근 사각형 배경 위 반원 게이지 + 노란 바늘)."""
    S = size * 4
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([0, 0, S - 1, S - 1], radius=S * 0.22, fill=CANVAS)
    cx, cy, r = S / 2, S * 0.66, S * 0.38
    lo = 0
    for hi, _, color in BANDS:
        d.arc([cx - r, cy - r, cx + r, cy + r], 180 + lo * 1.8 + 2, 180 + hi * 1.8 - 2, fill=color, width=round(S * 0.12))
        lo = hi
    import math
    ang = math.radians(180 + score * 1.8)
    nr, w = r * 0.62, round(S * 0.075)
    nx, ny = cx + nr * math.cos(ang), cy + nr * math.sin(ang)
    d.line([cx, cy, nx, ny], fill=PRIMARY, width=w)
    d.ellipse([nx - w / 2, ny - w / 2, nx + w / 2, ny + w / 2], fill=PRIMARY)
    d.ellipse([cx - S * 0.075, cy - S * 0.075, cx + S * 0.075, cy + S * 0.075], fill=PRIMARY)
    img.resize((size, size), Image.LANCZOS).save(path, optimize=True)


if __name__ == "__main__":
    docs = ROOT / "docs"
    render_icon(docs / "favicon-32.png", 32)
    render_icon(docs / "apple-touch-icon.png", 180)
    print("아이콘 생성 완료")
