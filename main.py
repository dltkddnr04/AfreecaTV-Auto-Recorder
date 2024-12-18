import os
import sys
import requests
import json
import time
import datetime
import platform
import subprocess
import threading
import signal

with open('config.json', 'r') as f:
    config = json.load(f)
    USER_NAME = config['user_name']
    USER_PASSWORD = config['user_password']

cookie_dict = None
server_domain = "sooplive.co.kr"

def id_or_login_detect(value):
    return value.isnumeric()

def get_id_from_login(user_login):
    get_cookie()
    url = f'https://live.{server_domain}/afreeca/player_live_api.php?bid={user_login}'
    data = {
        'bid': user_login,
        'type': 'live'
    }
    req = requests.post(url, data=data, cookies=cookie_dict)
    result = req.json()
    return result['CHANNEL']['BNO']

def get_login_from_id(user_id):
    get_cookie()
    url = f'https://live.{server_domain}/afreeca/player_live_api.php?bno={user_id}'
    data = {
        'bno': user_id,
        'type': 'live'
    }
    req = requests.post(url, data=data, cookies=cookie_dict)
    result = req.json()
    return result['CHANNEL']['BJID']

def console_print(message):
    time = datetime.datetime.today().strftime('%Y-%m-%dT%H-%M-%S')
    print("[{}] {}".format(time, message))

def get_cookie():
    global cookie_dict
    url = f"https://login.{server_domain}/app/LoginAction.php"
    data = {
        "szWork": "login",
        "szType": "json",
        "szUid": USER_NAME,
        "szPassword": USER_PASSWORD,
        "isSaveId": "true",
        "isSavePw": "false",
        "isSaveJoin": "false",
        "isLoginRetain": "Y"
    }

    req = requests.post(url, data=data)
    cookies = req.cookies
    cookie_dict = requests.utils.dict_from_cookiejar(cookies)

def stream_detect(user_id):
    url = f'https://live.{server_domain}/afreeca/player_live_api.php'
    data = {
        'bno': user_id,
        'type': 'live'
    }

    req = requests.post(url, data=data)
    result = json.loads(req.text)

    if 'RESOLUTION' in result['CHANNEL']:
        return True
    else:
        return False

def get_stream_m3u8_direct(user_id):
    url = f'https://live.{server_domain}/afreeca/player_live_api.php'
    data = {
        "bid": user_id,
        "quality": "original",
        "type": "aid",
        "pwd": "",
        "stream_type": "common",
    }

    req = requests.post(url, data=data, cookies=cookie_dict)
    result = req.json()

    if result['CHANNEL']['RESULT'] == 0:
        # 방송중이 아님
        return None
    elif result['CHANNEL']['RESULT'] == 1:
        # 방송중
        m3u8_url = f"https://live-global-cdn-v02.{server_domain}/live-stm-16/auth_playlist.m3u8?aid=" + result['CHANNEL']['AID']
        return m3u8_url
    elif result['CHANNEL']['RESULT'] == -6:
        # 로그인 필요
        get_cookie()
        return get_stream_m3u8_direct(user_id)
    else:
        # 알 수 없는 오류
        return None

def basic_file_info(user_login, extension):
    date = datetime.datetime.today().strftime('%Y-%m-%dT%H-%M-%S')
    path = './' + user_login + '/' + date + '.' + extension
    return path

def download_stream_m3u8_legacy(user_login, m3u8_url, extension):
    path = basic_file_info(user_login, extension)

    if platform.system() == "Windows":
        CREATE_NO_WINDOW = 0x08000000
        subprocess.run(["streamlink", m3u8_url, "best", "-o", path], creationflags=CREATE_NO_WINDOW)
    else:
        subprocess.run(["streamlink", m3u8_url, "best", "-o", path])#, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return

def download_stream_legay(user_login, extension):
    path = basic_file_info(user_login, extension)
    stream_url = f'https://play.{server_domain}/' + user_login

    if platform.system() == "Windows":
        CREATE_NO_WINDOW = 0x08000000
        subprocess.run(["streamlink", stream_url, "best", "-o", path, "--afreeca-username", USER_NAME, "--afreeca-password", USER_PASSWORD, "--afreeca-purge-credentials"], creationflags=CREATE_NO_WINDOW)
    else:
        subprocess.run(["streamlink", stream_url, "best", "-o", path, "--afreeca-username", USER_NAME, "--afreeca-password", USER_PASSWORD, "--afreeca-purge-credentials"])
    return

console_print("Program started")

try:
    user_info_list = sys.argv[1:]
    user_info = user_info_list[0]
except:
    console_print("Please input user login")

if len(user_info_list) == 0:
    user_info = input("Input streamer nickname(if you want to exit, press enter): ")
    if user_info == "":
        exit()

if len(user_info_list) > 1:
    console_print("only one streamer nickname is allowed")
    exit()

# if id_or_login_detect(user_info):
#     user_id = user_info
#     user_login = get_login_from_id(user_id)
# else:
#     user_login = user_info
#     user_id = get_id_from_login(user_login)

user_login = user_info

repeat_check = True
latest_error = ""

if not os.path.exists("{}".format(user_login)):
    os.makedirs("{}".format(user_login))

# 다운로드 프로세스 관리 변수
download_process = None
stop_download = False  # 종료 플래그

def input_thread():
    global stop_download, download_process
    while True:
        user_input = input("Press 'q' to stop downloading: ").strip().lower()
        if user_input == 'q':
            stop_download = True
            if download_process:
                # 다운로드 프로세스를 강제 종료
                download_process.terminate()
                console_print("Download process terminated.")
            break

# 사용자 입력 스레드 시작
threading.Thread(target=input_thread, daemon=True).start()

try:
    while not stop_download:
        # 스트림 확인 및 다운로드 시작
        stream_m3u8 = get_stream_m3u8_direct(user_login)
        if stream_m3u8 is not None:
            console_print(f"[{user_login}] Stream started")
            
            # 비차단 방식으로 subprocess 실행
            path = basic_file_info(user_login, "ts")
            command = [
                "streamlink", stream_m3u8, "best", "-o", path
            ]
            download_process = subprocess.Popen(command)

            # 다운로드가 종료될 때까지 대기
            download_process.wait()

            console_print(f"[{user_login}] Stream ended")
            download_process = None  # 다운로드 프로세스 초기화

        time.sleep(2)
except KeyboardInterrupt:
    stop_download = True
    if download_process:
        download_process.terminate()
    console_print("Program interrupted by user.")
