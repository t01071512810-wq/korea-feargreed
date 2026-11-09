# 한국 공포·탐욕 지수

CNN Fear & Greed Index를 한국 시장(KOSPI·KOSDAQ) 데이터로 옮긴 지수입니다. 지표마다 0~100점을 매기고 똑같은 비중으로 평균합니다.

| 지표 | 계산 | CNN 원본 |
|---|---|---|
| 시장 모멘텀 | KOSPI와 125일 이동평균의 괴리율 | S&P500 vs 125일선 |
| 주가 강도 | (52주 신고가 − 신저가 종목 수) / 종목 수 | NYSE 신고가/신저가 |
| 시장 폭 | McClellan 거래량 합산지수 | 동일 |
| 시장 변동성 | VKOSPI / 750일(약 3년) 평균, 점수도 750일 순위 (KRX) | VIX vs 50일선 |
| 풋/콜 비율 | 코스피200 옵션(위클리 포함, 정규장) 풋 ÷ 콜 **거래대금**, 5일 합계 (KRX). 거래량 기준은 폭락 때 반대로 움직여 쓰지 않음 | 풋/콜 비율 |
| 안전자산 수요 | KOSPI − 국고채10년 ETF(148070) 20일 수익률 차 | 주식 vs 국채 |
| 신용 스프레드 | 회사채 3년 AA− − 국고채 3년 금리 (ECOS, 키 필요) | 정크본드 스프레드 |

점수는 최근 252거래일 안에서의 백분위입니다(시장 변동성만 750거래일, 약 3년). VKOSPI와 풋/콜 비율은 [KRX OPEN API](https://openapi.krx.co.kr)(파생상품지수 시세정보, 옵션 일별매매정보)에서 받아 날짜별 요약을 `data/krx_daily.csv`에 쌓습니다. KRX는 그날 데이터를 저녁~다음 날 아침에 공개하므로 장 마감 직후 갱신에서는 전날 값을 쓰고 다음 날 아침에 확정됩니다. `KRX_API_KEY`가 없으면 KOSPI 실현변동성과 인버스÷레버리지 ETF 거래대금 비율로 대신합니다.

## 실행

```bash
pip install -r requirements.txt
python build.py          # 처음 실행 때 전 종목 과거 일봉을 받아 data/prices 에 캐시
```

`docs/data.json`이 만들어지면 `docs/index.html`을 정적 서버로 엽니다.

```bash
python -m http.server -d docs 8000
```

신용 스프레드 지표를 넣으려면 [ECOS](https://ecos.bok.or.kr/api/)에서 무료 인증키를 받아 `.env` 파일의 `ECOS_API_KEY=` 뒤에 넣습니다. KRX 키는 `KRX_API_KEY=`에 넣습니다(`.env`는 git에 올라가지 않습니다).

화면 디자인은 [awesome-design-md](https://github.com/VoltAgent/awesome-design-md)의 Binance 디자인 토큰을 참고했습니다.

## 자동 갱신

`.github/workflows/update.yml`이 GitHub Actions에서 평일 16:30 KST(장 마감 반영)와 다음 날 08:30 KST(회사채 금리·옵션 데이터 반영 후 확정)에 `build.py`를 돌리고 `docs/`의 결과물(data.json, og.png, index.html)을 커밋합니다. 커밋이 올라가면 Vercel이 자동으로 다시 배포합니다. GitHub 예약 실행은 몇 시간씩 늦어서, 제시간 실행은 [cron-job.org](https://cron-job.org)가 GitHub API의 `workflow_dispatch`를 호출합니다(Actions 쓰기 권한만 가진 토큰, 만료 시 재발급 필요). 저장소의 `schedule`은 예비용입니다. 저장소 설정에서 GitHub Pages를 `docs/` 폴더로 지정하고, Secrets에 `ECOS_API_KEY`와 `KRX_API_KEY`를 넣으면 됩니다.

참고용 지표이며 투자 권유가 아닙니다.

## 링크 미리보기와 아이콘

`build.py`가 매일 `docs/og.png`(오늘 점수·상태가 크게 보이는 1200×630 카드)를 그리고, `docs/index.html`의 `og:` 메타 태그를 오늘 값으로 바꿉니다. 카카오톡은 미리보기를 오래 캐시하므로 이미지 주소에 날짜(`?v=YYYYMMDD`)를 붙입니다. 바로 갱신이 안 보이면 [카카오 공유 디버거](https://developers.kakao.com/tool/debugger/sharing)에서 주소를 넣고 캐시를 지우면 됩니다.

탭 아이콘은 `docs/favicon.svg`, PNG 아이콘은 `python -m kfg.og`로 다시 만듭니다. 글꼴은 Noto Sans KR(SIL OFL, `assets/OFL.txt`)에서 ASCII와 자주 쓰는 한글 2,350자만 남긴 것입니다.
