import requests
import json

user_login = ''
url = f'https://live.sooplive.co.kr/afreeca/player_live_api.php'

data = {
    'bid': user_login,
    'type': 'live',
}

req = requests.post(url, data=data)
result = req.json()

# if json has 'VIEWPRESET' key, it means the user is live
if 'RESOLUTION' in result['CHANNEL']:
    print('live')
else:
    print('not live')

# with open(f'result({user_id}).json', 'w') as f:
#     json.dump(req.json(), f, ensure_ascii=False, indent=4)