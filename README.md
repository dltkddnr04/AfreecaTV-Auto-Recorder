# AfreecaTV-Auto-Recorder

SOOP(구 아프리카TV) 방송을 자동으로 녹화하는 Streamlink 기반 프로그램입니다. 방송이 켜질 때까지 기다렸다가 녹화하며, 방송 종료나 일시적인 연결 장애 이후에도 자동으로 다시 연결합니다.

## 요구사항

- Python **3.10 이상** (최신 Streamlink의 최소 요구사항)
- Streamlink 8.6.2 이상, 9 미만 (`requirements.txt`)

```bash
python -m pip install -r requirements.txt
```

## 사용 방법

1. 공개 방송은 계정 설정 없이도 실행할 수 있습니다. 로그인이나 성인 인증이 필요한 방송을 녹화하려면 `config.example.json`을 **`config.json`으로 복사**한 후 로그인 정보를 입력하세요. `config.json`은 Git 추적 대상에서 제외됩니다. 이미 옛 버전의 `config.json`을 수정해 사용 중이라면 업데이트 전에 반드시 백업하세요.

2. 방송인의 **채널 아이디**(표시 닉네임이 아닌 `play.sooplive.com/채널아이디`의 마지막 부분)를 사용합니다.

```bash
python main.py 채널아이디
```

3. 녹화 파일은 `./채널아이디/날짜-시간-고유값.ts`에 저장됩니다. `Ctrl+C` 또는 SIGTERM으로 녹화 프로세스를 함께 종료할 수 있습니다.

계정 정보를 파일 대신 `SOOP_USERNAME`, `SOOP_PASSWORD` 환경변수로 설정할 수도 있습니다. 두 값은 함께 설정하거나 모두 생략해야 합니다. 계정 정보는 Streamlink 프로세스 인자에 직접 넣지 않고 임시 권한 제한 설정 파일을 사용합니다. 외부 프로세스를 관리할 수 있는 관리자에게까지 숨겨지는 것은 아닙니다.

## 연결 복구와 설정

CDN 선택 및 HLS/인증 토큰은 Streamlink의 SOOP 플러그인에 위임합니다. 재시도 간격, 횟수, 네트워크 타임아웃을 환경변수로 조정할 수 있습니다.

| 환경변수 | 기본값 | 의미 |
| --- | ---: | --- |
| `CHECK_INTERVAL` | 20 | 방송 탐색 재시도 간격(초) |
| `RETRY_MAX` | 4 | 탐색 시 추가 재시도 횟수 |
| `HTTP_TIMEOUT` | 15 | HTTP 요청 타임아웃(초) |
| `STREAM_TIMEOUT` | 90 | 새 스트림 데이터 대기 타임아웃(초) |
| `SEGMENT_TIMEOUT` | 20 | 세그먼트 다운로드 시작 대기 타임아웃(초) |
| `SEGMENT_ATTEMPTS` | 5 | 세그먼트별 최대 시도 횟수 |

Streamlink 종료 후 10초에서 최대 300초까지 장애 빈도에 따라 대기 시간이 증가하며, 60초 이상 진행된 세션 뒤에는 초기화됩니다. 이전 녹화 파일을 덮어쓰지 않습니다. 연결 단절 구간의 영상 손실이나 소스 측 결함까지 복구할 수 있다는 뜻은 아닙니다.

## 제한 사항

- 현재 구현은 Streamlink가 지원하는 **SOOP HLS 녹화** 방식입니다. Grid P2P 녹화는 지원하지 않습니다.
- Streamlink 플러그인이나 SOOP 인증 정책이 바뀌면 업데이트가 필요할 수 있습니다.
- 방송 중 접근 권한이 거부되거나 국가/연령/유료/비밀번호 제한이 적용된 경우에는 해당 계정의 정상적인 접근 권한이 필요합니다.
- 방송 탐색 중 Streamlink가 반복 실패하면 프로그램이 계속 재시도하므로 콘솔의 오류 내용을 확인하세요.

## 테스트

```bash
python -m unittest discover -s tests -v
```

## 라이선스

MIT. [LICENSE](LICENSE) 참조.
