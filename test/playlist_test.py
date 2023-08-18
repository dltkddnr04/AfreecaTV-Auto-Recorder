import requests
import json

url = 'https://pc-web.stream.afreecatv.com/live-stmc-39/auth_playlist.m3u8?aid=.A32.7bbT56vyHM9fKZk.r9GKax0ypAsQXT5QLrM70w8Kn20298DeXNGXBMyjBLIbJmr1LjVGPZSW1Ff75tQ0hYykMz-8UexlWw8ZuHQzkg'
cookies = {
    "_ausa": "0xeb8d3156",
    "_ausb": "0xd64137e7",
    "_ga_9PY781H32Y": "GS1.1.1692275795.1.1.1692277012.59.0.0",
    "_ga": "GA1.1.100886699.1692275796",
    "_ga_KV34D9945N": "GS1.2.1692276835.3.1.1692277011.0.0.0",
    "_gid": "GA1.2.229982708.1692275765",
    "perferCategory": "dltkddnr04=",
    "NextChangePwd": "1",
    "PdboxBbs": "dltkddnr04",
    "PdboxTicket": ".A32.7bbT56vyHM9fKZk.18z5qSfWDSR1u5VFcTJamPob2kuy-XgKxJjEEb6HcLUABmy1D7pfKx2iK7F8f4JM_joHnhZATV5c8NYu2Xno87wSaoeTJ2mKTdPxQIpIefCGsMZX_6B8KL5qxKiWSEa4IcamqcZqWpe4ETWeppmE_yW6vXT43ilEDqFlbjC_LB4Trejdp9s13u9nPi8p_aw4vVYuw9W2WUXBuK_SjhNF4Ka73d5SN2F1isMnKJXWLKQTUNzeQu4hLvLcVmvg_0BRVjRBUmj8cleeKepw_WkwSrdHeuXvqSlDjUXG6QeA_LpAkdImeULfCXbBRmP1dsuRw8ziBjelEi5DsoL09r__4ELVplMrBXjaDl-IilMv77yVRWUzpnCCvIIgdDXtuNsTPJXZcaZpTITJHOQ-M0pxbohQowBWxr8LFUR1lkhaidt7NeeTDKVqt_L7qeIH2CTXAWIKxSNE_Kud-tjWHuAJ83Lk4GTzxsQm9Glet1UO4pZAL5vpgq0D_ELulV5k6v6zaPJNDOsRJb7ujQzkOLVD1MN278OoDPMUgpcdZibiabv67E_y1IhxQW-U4F97Ir7FqPwtpJoZnfhJ3088RGlhjw",
    "PdboxUser": "uid%3Ddltkddnr04%26uno%3D35168015%26age%3D19%26sex%3DA%26A%3DAAB%26B%3DBABJ%26unick%3D%EB%B6%81%EC%AA%BD%EC%9D%98%EC%99%95%EC%9E%90%26apply_date%3D1433500773%26name_chk%3D1%26sess_adult_chk%3D1%26broad_name_chk%3D1%26change_password%3D1%26chnnl_cd%3D1%26chnnl_name_chk%3D1",
    "RDB": "c80300000000004b520000000000000000000000000000000100000013130000000000000001",
    "isBbs": "1",
    "_ga_5EYT9PM505": "GS1.1.1692275791.1.1.1692275800.0.0.0",
    "AbroadChk": "FAIL",
    "AbroadVod": "FAIL",
    "bjStationHistory": "%0224839512%0225042926%026637188%0220533472%0217249074%0219666134%0212888297%0221925884%0217592658",
    "_au": "12f76ade10e9365bc5f25773510c5907",
    "_au3rd": "12f76ade10e9365bc5f25773510c5907"
}
req = requests.get(url, cookies=cookies)

print(req.status_code)