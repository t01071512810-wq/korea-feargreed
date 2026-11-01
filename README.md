# 한국 공포·탐욕 지수

CNN Fear & Greed Index를 한국 시장(KOSPI·KOSDAQ) 데이터로 옮긴 지수입니다. 지표마다 0~100점을 매기고 똑같은 비중으로 평균합니다.

| 지표 | 계산 | CNN 원본 |
|---|---|---|
| 시장 모멘텀 | KOSPI와 125일 이동평균의 괴리율 | S&P500 vs 125일선 |
| 주가 강도 | (52주 신고가 − 신저가 종목 수) / 종목 수 | NYSE 신고가/신저가 |
| 시장 폭 | McClellan 거래량 합산지수 | 동일 |
| 시장 변동성 | KOSPI 20일 실현변동성 / 50일 평균 (VKOSPI 대용) | VIX vs 50일선 |
| 안전자산 수요 | KOSPI − 국고채10년 ETF(148070) 20일 수익률 차 | 주식 vs 국채 |
| 신용 스프레드 | 회사채 3년 AA− − 국고채 3년 금리 (ECOS, 키 필요) | 정크본드 스프레드 |

점수는 최근 252거래일 안에서의 백분위입니다. 풋/콜 비율과 VKOSPI는 KRX 로그인이 필요해 빠져 있습니다.

## 실행

```bash
pip install -r requirements.txt
python build.py          # 처음 실행 때 전 종목 과거 일봉을 받아 data/prices 에 캐시
```

`docs/data.json`이 만들어지면 `docs/index.html`을 정적 서버로 엽니다.

```bash
python -m http.server -d docs 8000
```

신용 스프레드 지표를 넣으려면 [ECOS](https://ecos.bok.or.kr/api/)에서 무료 인증키를 받아 `.env` 파일의 `ECOS_API_KEY=` 뒤에 넣습니다(`.env`는 git에 올라가지 않습니다).

화면 디자인은 [awesome-design-md](https://github.com/VoltAgent/awesome-design-md)의 Binance 디자인 토큰을 참고했습니다.

## 자동 갱신

`.github/workflows/update.yml`이 GitHub Actions에서 평일 16:30 KST(장 마감 반영)와 다음 날 08:30 KST(회사채 금리 반영 후 확정)에 `build.py`를 돌리고 `docs/data.json`을 커밋합니다. 저장소 설정에서 GitHub Pages를 `docs/` 폴더로 지정하고, Secrets에 `ECOS_API_KEY`를 넣으면 됩니다.

참고용 지표이며 투자 권유가 아닙니다.
