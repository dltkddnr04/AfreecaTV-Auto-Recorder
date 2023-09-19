import requests
import json

# user_login = 'berryoonna'
user_id = '248302062'
url = f'https://live.afreecatv.com/afreeca/player_live_api.php'
data = {
    'bno': user_id,
    'type': 'live'
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