# AfreecaTV-Auto-Recorder (SOOP)

**유지보수 종료 예정 · CLI 전용.** 공식
[Streamlink](https://streamlink.github.io/) SOOP 플러그인으로 방송을 저장하는
작은 래퍼입니다. Grid/P2P, 커스텀 API/CDN 구현, 고급 아카이브 기능은
이 저장소에서 다루지 않습니다. 그런 기능은
[Integrated Recorder](https://github.com/dltkddnr04/Integrated-Recorder)의 역할입니다.

## 실행

Python 3.10+ 및 Streamlink 8.6.2+:

```sh
python -m pip install -r requirements.txt
python main.py CHANNEL
python main.py CHANNEL_A CHANNEL_B
```

공개 방송은 계정이 필요 없습니다. 로그인이 필요한 경우 `config.example.json`을
`config.json`으로 복사해 `user_name`, `user_password`를 설정하거나
`SOOP_USERNAME`, `SOOP_PASSWORD` 환경 변수를 함께 지정합니다.
비밀번호는 프로세스 인자가 아닌 권한 제한 임시 Streamlink 설정 파일로 전달하며
정상 종료 시 삭제합니다. `config.json`은 Git에 포함되지 않습니다.
보호된 방송의 접근 권한을 우회하지 않습니다.

방송이 오프라인이거나 연결이 끊어지면 기본 10초 후 재시도합니다.
`Ctrl+C`/SIGTERM으로 종료합니다. Python 프로세스 자체가 종료되거나 PC가
재부팅되면 외부 OS 서비스 관리자에서 재시작해야 합니다.

녹화는 현재 작업 디렉터리의 `CHANNEL/` 아래에 저장됩니다.
TS/fMP4는 `.ts`/`.mp4`, 알 수 없는 원본은 `.raw`로 보존합니다.
강제 종료 후 남은 `.capture` 파일은 삭제하지 않습니다.
**실제로 수신하지 못한 방송 구간이나 A/V 무결성은 복구·보증하지 않습니다.**

| 환경 변수 | 기본값 | 설명 |
| --- | ---: | --- |
| `CHECK_INTERVAL` | 10 | 오프라인·오류 후 재시도 초 |
| `STARTUP_TIMEOUT` | 120 | 스트림 시작 후 첫 데이터까지 허용할 초 |
| `STALL_TIMEOUT` | 180 | 마지막 파일 증가 후 허용할 초 |
| `HTTP_TIMEOUT` | 15 | Streamlink HTTP 요청 타임아웃 초 |

테스트: `python -m unittest discover -s tests -v`

MIT License. [LICENSE](LICENSE)
