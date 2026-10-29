# AfreecaTV-Auto-Recorder (SOOP)

**CLI 전용 / 아카이브 준비 중.** Streamlink를 간결하고 안정적으로 실행하는 자동 녹화기입니다. 방송 수신은 [source.soop의 외부 `soop_grid` 플러그인](https://github.com/integrated-recorder/source.soop/tree/main/tests/streamlink-grid-poc)에 전부 위임합니다. 자체 Grid 프로토콜·HLS·CDN 구현을 포함하지 않습니다.

## 준비

- Python 3.10+ / Streamlink 8.6.2 권장
- `source.soop/tests/streamlink-grid-poc/dist/soop_grid.py`를 **`soop_grid.py`라는 파일명**으로 Streamlink 사용자 플러그인 디렉터리에 설치
- Streamlink 내장 `soop` 플러그인을 교체하지 말 것. `plugins/soop_grid.py`는 소스 진입점이며, 단독 설치 파일은 `dist/soop_grid.py`임

설치 경로 및 검증 절차: [source.soop 공식 설치 가이드](https://github.com/integrated-recorder/source.soop/blob/main/tests/streamlink-grid-poc/docs/COMMUNITY_GUIDE_KO.md).

설치 후 확인:

```sh
python -m pip install -r requirements.txt
streamlink --plugins
# 설치된 플러그인 목록에 soop_grid가 표시되어야 합니다.
```

CLI는 시작 시 `streamlink --plugins`로 `soop_grid`의 존재를 검사하고, 없다면 **내장 SOOP HLS로 조용히 대체하지 않고 즉시 오류로 종료**합니다.

## 실행

```sh
python main.py CHANNEL_ID
python main.py CHANNEL_A CHANNEL_B
python main.py CHANNEL_ID --bno 123456
python main.py CHANNEL_ID --transport grid
python main.py CHANNEL_ID --transport hls
```

| 전송 모드 | Streamlink에 전달하는 값 | 스트림 선택 |
| --- | --- | --- |
| `auto` (기본값) | `--soop-grid-transport auto` | `original` |
| `grid` | `--soop-grid-transport grid` | `original` |
| `hls` | `--soop-grid-transport hls` | `best` |

`auto`는 Grid 우선이며 **미디어 수신 이전의 허용된 연결 장애**에서만 공식 HLS로 fallback합니다. 이미 받은 Grid와 HLS 데이터를 연결하지 않습니다. `--bno`는 단일 채널의 특정 방송 번호를 선택할 때 사용합니다.

### 인증

공개 방송에는 계정이 필요하지 않습니다. 계정이 필요한 방송은 다음 환경변수를 설정합니다.

```sh
export SOOP_ACCOUNT_ID='YOUR_ACCOUNT'
export SOOP_ACCOUNT_PASSWORD='YOUR_PASSWORD'
# 비밀번호 방송만 필요할 때:
export SOOP_STREAM_PASSWORD='BROADCAST_PASSWORD'
python main.py CHANNEL_ID
```

또는 기존 `config.example.json`을 `config.json`으로 복사해 `user_name` / `user_password` (필요하면 `stream_password`)를 지정합니다. 이전 환경변수 `SOOP_USERNAME` / `SOOP_PASSWORD`도 호환됩니다. 전송 모드는 `--transport`, `SOOP_GRID_TRANSPORT`, `config.json`의 `transport` 순서로 적용합니다.

**중요:** 외부 플러그인은 내장 SOOP용 `--soop-username` / `--soop-password`를 읽지 않습니다. 이 CLI는 계정·방송 비밀번호를 플러그인이 지원하는 `SOOP_ACCOUNT_ID` / `SOOP_ACCOUNT_PASSWORD` / `SOOP_STREAM_PASSWORD`로 **Streamlink 자식 프로세스에만 전달**합니다. 비밀번호를 명령행 옵션이나 임시 설정 파일에 쓰지 않습니다.

## 장애 처리

- 오프라인·녹화 종료·실패 뒤 기본 10초 간격으로 재시도합니다.
- `STARTUP_TIMEOUT` 기본 120초, `STALL_TIMEOUT` 기본 180초: 파일 출력이 없거나 정체되면 Streamlink를 재실행합니다.
- `HTTP_TIMEOUT` 기본 15초; 나머지 HLS 세그먼트 재시도·수신은 Streamlink가 처리합니다.
- 출력은 작업 디렉터리의 `CHANNEL_ID/`에 고유 파일명으로 저장됩니다. TS/fMP4는 형식별 확장자로 저장하고, 분류 불가능한 데이터는 `.raw`로 보존합니다.
- Ctrl+C/SIGTERM을 처리합니다. Python 프로세스 자체가 죽거나 PC가 재부팅되면 외부 서비스 관리자(systemd 등)에서 재시작해야 합니다.

플러그인은 아직 **Experimental/Beta**입니다. Grid의 코덱·타임스탬프 미지원 조건에서 안전하게 실패할 수 있고 모든 방송에서의 무손실 수신을 보장하지 않습니다. 이 CLI는 누락된 미디어·코덱 불일치를 자체 복구하지 않습니다.

## 검증

```sh
python -m unittest discover -s tests -v
```

CI는 인자·환경변수·장애 경계의 단위 테스트입니다. **외부 플러그인 설치 및 실제 SOOP 장시간 녹화 성공은 CI에서 검증하지 않습니다.**

MIT License — [LICENSE](LICENSE). 외부 플러그인 구현 및 배포 파일은 별도 **AGPL-3.0-only**입니다. 이 저장소에는 포함하지 않습니다.
