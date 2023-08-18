import os
import sys
import requests
import json
import time
import datetime
import streamlink
import platform
import subprocess

# 여기에 아이디와 비밀번호를 입력해주세요.
user_name = "dltkddnr04"
user_password = "2pN-Wsf-uCH-k4g"

def console_print(message):
    time = datetime.datetime.today().strftime('%Y-%m-%d %H:%M:%S')
    print("[{}] {}".format(time, message))

def stream_detect(user_login):
    url = f'https://live.afreecatv.com/afreeca/player_live_api.php?bjid={user_login}'
    data = {
        'bid': user_login,
        'type': 'live'
    }

    req = requests.post(url, data=data)
    result = json.loads(req.text)

    if 'RESOLUTION' in result['CHANNEL']:
        return True
    else:
        return False

def get_stream_m3u8_streamlink(user_login):
    stream_url = "play.afreecatv.com/" + user_login
    streams = streamlink.streams(stream_url)
    
    list = {}
    for key, value in streams.items():
        list[key] = value.url

    return list

def basic_file_info(user_login, extension):
    date = datetime.datetime.today().strftime('%Y-%m-%d %H-%M-%S')
    path = './' + user_login + '/' + date + '.' + extension
    return path

def download_stream_legacy(user_login, extension):
    path = basic_file_info(user_login, extension)
    stream_url = 'https://play.afreecatv.com/' + user_login

    if platform.system() == "Windows":
        CREATE_NO_WINDOW = 0x08000000
        subprocess.run(["streamlink", stream_url, "best", "-o", path, "--afreeca-username", user_name, "--afreeca-password", user_password, "--afreeca-purge-credentials"], creationflags=CREATE_NO_WINDOW)
    else:
        subprocess.run(["streamlink", stream_url, "best", "-o", path, "--afreeca-username", user_name, "--afreeca-password", user_password, "--afreeca-purge-credentials"])
    return

console_print("Program started")

try:
    user_login_list = sys.argv[1:]
except:
    console_print("Please input user login")
    exit()

if len(user_login_list) == 0:
    console_print("streamer nickname is not exist")
    exit()

if len(user_login_list) > 1:
    console_print("only one streamer nickname is allowed")
    exit()

user_login = user_login_list[0]

repeat_check = True
latest_error = ""

if not os.path.exists("{}".format(user_login)):
    os.makedirs("{}".format(user_login))

while True:
    try:
        if repeat_check:
            console_print("[{user_login}] Waiting to start streaming".format(user_login=user_login))
            repeat_check = False
        
        if stream_detect(user_login):
            console_print("[{user_login}] Stream started".format(user_login=user_login))
            try:
                download_stream_legacy(user_login, "ts")
            except Exception as e:
                # print("Error: {}".format(e))
                continue

            console_print("[{user_login}] Stream ended".format(user_login=user_login))
            repeat_check = True

    except Exception as e:
        if latest_error != e:
            console_print("Error: {}".format(e))
            latest_error = e

    time.sleep(2)