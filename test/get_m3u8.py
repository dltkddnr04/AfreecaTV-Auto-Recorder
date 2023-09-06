import requests

username = "" # 계정 아이디
password = "" # 계정 비번
stream_username = "" # 방송 아이디
stream_password = "" # 비번방 비번
quality = "original" # original, hd, sd

# 성인방송 시청을 위한 세션 생성
url = "https://login.afreecatv.com/app/LoginAction.php"
data = {
    "szWork": "login",
    "szType": "json",
    "szUid": username,
    "szPassword": password,
    "isSaveId": "true",
    "isSavePw": "false",
    "isSaveJoin": "false",
    "isLoginRetain": "Y"
}

req = requests.post(url, data=data)
cookies = req.cookies
cookie_dict = requests.utils.dict_from_cookiejar(cookies)

# m3u8 url 요청
url = f'https://live.afreecatv.com/afreeca/player_live_api.php'
data = {
    "bid": stream_username,
    "quality": quality,
    "type": "aid",
    "pwd": stream_password,
    "stream_type": "common",
}

req = requests.post(url, data=data, cookies=cookie_dict)
result = req.json()
print("https://live-global-cdn-v02.afreecatv.com/live-stm-16/auth_playlist.m3u8?aid=" + result['CHANNEL']['AID'])