# AfreecaTV-Auto-Recorder
아프리카티비 방송 자동 다운로드 프로그램

## 사용법

### 직접 실행

1. config.json 파일을 편집기로 열어서 아이디와 비밀번호를 입력해주세요.
```json
{
    "user_name": "본인_아이디",
    "user_password": "본인_비밀번호"
}
```

2. main.py 파일을 실행시키면서 인자로 다운로드 받을 방송인의 닉네임을 입력해주세요.
```bash
python3 main.py 방송인의_닉네임
```

3. 컴퓨터를 계속 켜놓고 있어야 다운로드가 가능합니다.<br>방송이 시작되면 해당 폴더에 자동으로 다운로드를 시작합니다.<br>브라우저에서 아프리카티비 창은 켜놓고 있지 않아도 됩니다.

### Docker로 실행

1. Dockerfile로 빌드합니다.
```bash
docker build -t myname/afreecatv-auto-recorder:latest .
```

2. 빌드한 이미지를 실행합니다.
```bash
docker run -it -v /my/path:/app/STREAMER_NAME -e USER_NAME=user_name -e USER_PASSWORD=user_password myname/afreecatv-auto-recorder:latest STREAMER_NAME
```

3. 각 환경변수의 설명은 아래와 같습니다.

| property       | category    | type   | required | description                          |
|----------------|-------------|--------|----------|--------------------------------------|
| USER_NAME      | environment | string | true  | 자신의 afreecatv id                     |
| USER_PASSWORD  | environment | string | true    | 자신의 afreecatv password               |
| RETRY_INTERBAL | environment |  int   | false   | 방송 여부 확인 시, 재시도를 하는 간격. 초 단위, 기본값 60 |
| STREAMER_NAME | command argument | string | true | 녹화하고자 하는 BJ의 id |

4. 백그라운드로 실행하려면 `-d` 옵션을 사용하면 됩니다.
```bash
docker run -e USER_NAME=user_name -e USER_PASSWORD=user_password -e STREAMER=streamer myname/afreecatv-auto-recorder:latest -d
```


## 요구사항
- Python 3.6 이상
- requests
- [streamlink](https://streamlink.github.io)