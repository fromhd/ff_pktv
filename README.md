# ff_pktv

FlaskFarm (SJVA) Plugin for PopkonTV (팝콘TV)

팝콘TV 실시간 방송 목록 수집, M3U 플레이리스트 생성 및 스트리밍 재생 지원 플러그인입니다.

## 저장소 (Repository)
- GitHub: [https://github.com/fromhd/ff_pktv](https://github.com/fromhd/ff_pktv)
- 원출처 (Original Repository): [https://github.com/ssagajikorea/ff_pktv](https://github.com/ssagajikorea/ff_pktv) (by ssagajikorea)

## 주요 기능
- 최신 PopkonTV Next.js REST API 연동
- 실시간 방송 채널 목록 자동 조회 (페이지네이션 지원)
- M3U 플레이리스트 및 Plex용 YAML 생성
- HLS M3U8 스트림 실시간 URL 발급 및 재생 (Redirect, Direct, Proxy 모드 지원)
- 회원 로그인 인증 지원 (성인 방송 시청)
- 방송 세션 코드(`pkCastCode`) 자동 동기화 및 재시도 지원

## 설치 방법 (FlaskFarm)
1. FlaskFarm 관리자 페이지 접속
2. **플러그인 > 플러그인 설치 (Git)** 메뉴 이동
3. Git 주소에 `https://github.com/fromhd/ff_pktv` 입력 후 설치
4. 플러그인 목록에서 `ff_pktv` 활성화