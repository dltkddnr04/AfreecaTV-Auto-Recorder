# AfreecaTV-Auto-Recorder
트위치 방송 자동 다운로드 프로그램

## 사용법
1. main.py 파일을 편집기로 열어서 11 ~ 12 번째줄 아이디와 비밀번호를 본인의 아이디와 비밀번호로 수정해주세요.
```python
# 여기에 아이디와 비밀번호를 입력해주세요.
user_name = "본인의_아프리카티비_아이디"
user_password = "본인의_아프리카티비_비밀번호"
```

2. main.py 파일을 실행시키면서 인자로 다운로드 받을 방송인의 닉네임을 입력해주세요.
```bash
python3 main.py 방송인의_닉네임
```

3. 컴퓨터를 계속 켜놓고 있어야 다운로드가 가능합니다. 방송이 시작되면 자동으로 다운로드를 시작합니다.

## 요구사항
- Python 3.6 이상
- [streamlink](https://streamlink.github.io)