import requests

USERNAME = "" # 계정 아이디
PASSWORD = "" # 계정 비번
STREAM_ID = "" # 방송 계정 내부 아이디값
STREAM_USERNAME = "" # 방송 아이디
STREAM_PASSWORD = "" # 비번방 비번
QUALITY = "original" # original, hd, sd

# 성인방송 시청을 위한 세션 생성
url = "https://login.afreecatv.com/app/LoginAction.php"
data = {
    "szWork": "login",
    "szType": "json",
    "szUid": USERNAME,
    "szPassword": PASSWORD,
    "isSaveId": "true",
    "isSavePw": "false",
    "isSaveJoin": "false",
    "isLoginRetain": "Y"
}

req = requests.post(url, data=data)
cookies = req.cookies
cookie_dict = requests.utils.dict_from_cookiejar(cookies)
# print(cookie_dict)

# m3u8 url 요청
url = 'https://live.afreecatv.com/afreeca/player_live_api.php'
# 방송 내부 아이디로 방송 정보를 가져옴
data = {
    "bno": STREAM_ID,
    "quality": QUALITY,
    "type": "aid",
    "pwd": STREAM_PASSWORD,
    "stream_type": "common",
}
# 방송 아이디로 방송 정보를 가져옴
data = {
    "bid": STREAM_USERNAME,
    "quality": QUALITY,
    "type": "aid",
    "pwd": STREAM_PASSWORD,
    "stream_type": "common",
}

req = requests.post(url, data=data, cookies=cookie_dict)
result = req.json()

if result['CHANNEL']['RESULT'] == 0:
    print("방송중이 아님")
elif result['CHANNEL']['RESULT'] == 1:
    m3u8_url = "https://live-global-cdn-v02.afreecatv.com/live-stm-16/auth_playlist.m3u8?aid=" + result['CHANNEL']['AID']
    print(m3u8_url)
elif result['CHANNEL']['RESULT'] == -6:
    print("로그인 필요")
else:
    print("알 수 없는 오류")