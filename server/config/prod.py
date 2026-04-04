import re
import os
import requests

from flask import request, redirect, Response
from random import shuffle
from constants import CONFIG_PATH
from utils import read_json, write_json, dump_json, get_memory


def randomHash():

    hash  = list("abcdef")
    shuffle(hash)

    return ''.join(hash)


def prodRefreshConfig():

    data = {
        "resVersion": None
    }

    return data, 200


def prodAndroidVersion(subpath=None):

    server_config = get_memory("config")
    version = server_config["version"]["android"]

    if server_config["assets"]["enableMods"]:
        version["resVersion"] = version["resVersion"][:18] + randomHash()

    return version

def redirect_rote():
    return redirect("/config/prod/official/network_config")

def prodNetworkConfig_new():
    server_config = get_memory("config")
    if server_config["server"]["adaptive"]:
        server = request.host_url[:-1]
    else:
        server = (
            "http://"
            + server_config["server"]["host"]
            + ":"
            + str(server_config["server"]["port"])
        )

    result = server_config["networkConfig"]["cn_new"]
    for index in result:
        if isinstance(result[index], str) and result[index].find("{server}") >= 0:
            result[index] = re.sub("{server}", server, result[index])

    return result

def prodNetworkConfig():

    server_config = get_memory("config")

    mode = server_config["server"]["mode"]
    server = request.host_url[:-1]
    network_config = server_config["networkConfig"][mode]
    funcVer = network_config["content"]["funcVer"]

    if server_config["assets"]["autoUpdate"]:
        if mode == "cn":
            version = requests.get("https://ak-conf.hypergryph.com/config/prod/official/Android/version", verify=False)
        elif mode == "global":
            version = requests.get("https://ark-us-static-online.yo-star.com/assetbundle/official/Android/version", verify=False)
        server_config["version"]["android"] = version

        write_json(server_config, CONFIG_PATH)

    for index in network_config["content"]["configs"][funcVer]["network"]:
        url = network_config["content"]["configs"][funcVer]["network"][index]
        if isinstance(url, str) and url.find("{server}") >= 0:
            network_config["content"]["configs"][funcVer]["network"][index] = re.sub("{server}", server, url)

    result = network_config.copy()
    result["content"] = dump_json(result["content"])
    result = dump_json(result)
    return result


def prodRemoteConfig():

    remote:dict = get_memory("config")["remote"].copy()
    return dump_json(remote)

def prodAudit(subpath):

        response = requests.get(f"https://ak-asset.hypergryph.com/audit/official/Windows/{subpath}", verify=False)
        return response.json()

    # TODO: 等windows版本数据可以自动更新后再用
    # server_config = get_memory("config")
    # result = server_config["version"]["windows"]

    # return result


def prodPreAnnouncement():

    server_config = get_memory("config")
    mode = server_config["server"]["mode"]
    match mode:
        case "cn":
            data = requests.get("https://ak-conf.hypergryph.com/config/prod/announce_meta/Android/preannouncement.meta.json", verify=False)
        case "global":
            data = requests.get("https://ark-us-static-online.yo-star.com/announce/Android/preannouncement.meta.json", verify=False)
        case _:
            data = requests.get("https://ak-conf.hypergryph.com/config/prod/announce_meta/Android/preannouncement.meta.json", verify=False)

    return data


def prodAnnouncement():

    server_config = get_memory("config")
    mode = server_config["server"]["mode"]
    match mode:
        case "cn":
            data = requests.get("https://ak-conf.hypergryph.com/config/prod/announce_meta/Android/preannouncement.meta.json", verify=False)
        case "global":
            data = requests.get("https://ark-us-static-online.yo-star.com/announce/Android/preannouncement.meta.json", verify=False)
        case _:
            data = requests.get("https://ak-conf.hypergryph.com/config/prod/announce_meta/Android/preannouncement.meta.json", verify=False)

    return data

def prodGateMeta():
    return {
        "preAnnounceId": "478",
        "actived": True,
        "preAnnounceType": 2
    }

def get_latest_game_info():

    server_config = get_memory("config")
    mode = server_config["server"]["mode"]
    match mode:
        case "cn":
            version = server_config["version"]["android"]
        case "global":
            version = server_config["versionGlobal"]["android"]
        case _:
            version = server_config["version"]["android"]
    funcVer = server_config["networkConfig"][mode]["content"]["funcVer"]

    main_version  = funcVer.lstrip("V").lstrip("0") or "0"[:2]

    result = {
        "version": f"{main_version}.0.0",
        "action": 0,
        "update_type": 0,
        "state": 0,
        "update_info": {
            "package": None,
            "patch": None,
            "custom_info": "",
            "source_package": None
        },
        "client_version": version["clientVersion"]
    }

    return result

def ak_sdk_config():
    return {"report_device_info": 10000}

def prodGameBulletin():
    # return redirect("https://ak-webview.hypergryph.com/gameBulletin")
    return """
    <!doctype html>
    <html lang="zh-cn">
    
    <head>
        <meta name="referrer" content="no-referrer">
        <meta charset="utf-8">
        <meta http-equiv="pragma" content="no-cache">
        <meta http-equiv="cache-control" content="no-cache">
        <meta http-equiv="X-UA-Compatible" content="IE=edge,chrome=1">
        <meta name="renderer" content="webkit">
        <meta name="force-rendering" content="webkit">
        <meta name="viewport" content="user-scalable=no,initial-scale=1,maximum-scale=1,minimum-scale=1,width=device-width,height=device-height,viewport-fit=cover">
        <meta name="copyright" content="Hypergryph">
        <meta name="format-detection" content="telephone=no,email=no,address=no">
        <meta name="apple-mobile-web-app-capable" content="yes">
        <meta name="robots" content="noindex">
        <title>公告 | 明日方舟 - Arknights</title>
        <link href="https://web.hycdn.cn/arknights/webview/favicon.ico" rel="icon">
        <link as="image" href="https://web.hycdn.cn/arknights/webview/assets/img/header.bb67d4.png" rel="preload">
        <link as="image" href="https://web.hycdn.cn/arknights/webview/assets/img/rhodes.739d79.png" rel="preload">
        <link href="https://web.hycdn.cn/arknights/webview/commons.5dd297.css" rel="stylesheet">
        <link href="https://web.hycdn.cn/arknights/webview/game.77fefb.css" rel="stylesheet">
    </head>
    
    <body>
        <div id="root">
        </div>
        <script crossorigin="anonymous" src="https://web.hycdn.cn/arknights/webview/analytics.1585a3.js">
        </script>
        <script crossorigin="anonymous" src="https://web.hycdn.cn/arknights/webview/game_i18n.bb363a.js">
        </script>
        <script crossorigin="anonymous" src="https://web.hycdn.cn/arknights/webview/react.0bb887.js">
        </script>
        <script crossorigin="anonymous" src="https://web.hycdn.cn/arknights/webview/commons.cd79f1.js">
        </script>
        <script crossorigin="anonymous" src="https://web.hycdn.cn/arknights/webview/game.130b53.js">
        </script>
    </body>

    </html>
    """

def prodAnalyticsCollect():
    return {
        "status": 0,
        "code": 0,
        "msg": "",
        "data": {}
    }

def prodGameBulletin():
    import hashlib
    from datetime import datetime
    # 已经做好了，不要改！就是index.html文件！不要改！
    header = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/105.0.0.0 Safari/537.36 Edg/105.0.1343.53"
    }
    cache_path = os.path.abspath("./assets/ak-webview/gameBulletin/")
    arch = request.args.get("target", None)
    if arch is None:
        arch = "Android"

    if True:
        file = requests.get(f"https://ak-webview.hypergryph.com/gameBulletin?target={arch}", stream=True, verify=False, headers=header)

        if file.status_code == 200:
            if not os.path.exists(cache_path):
                os.makedirs(cache_path)

            if os.path.exists(f"{cache_path}/index.html"):
                with open(f"{cache_path}/index.html", "rb") as old_file:
                    old_file_md5 = hashlib.md5(old_file.read()).hexdigest()
                
                current_file_md5 = hashlib.md5(file.content).hexdigest()

                if old_file_md5 != current_file_md5:
                    os.rename(f"{cache_path}/index.html", f"{cache_path}/index.{datetime.now().strftime('%Y%m%d%H%M%S')}.html")
                
                    with open(f"{cache_path}/index.html", "wb") as f:
                        for chunk in file.iter_content(chunk_size=1024):
                            if chunk:
                                f.write(chunk)

    server_config = get_memory("config")
    if server_config["server"]["adaptive"]:
        server = request.host_url.rstrip("/")
    else:
        server = f"http://{server_config['server']['host']}:{server_config['server']['port']}"

    with open(f"{cache_path}/index.html", encoding="utf-8") as f:
        content = f.read()
    content = content.replace("https://web.hycdn.cn", server)
    # 返回响应，保留 Content-Type
    content_type = "text/html; charset=utf-8"
    return Response(content, content_type=content_type)

def prodBulletinList(subpath):
    from urllib.parse import quote
    header = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/105.0.0.0 Safari/537.36 Edg/105.0.1343.53"
    }
    cache_path = os.path.abspath("./assets/ak-webview/api/game/")

    if not os.path.isdir(cache_path):
        os.makedirs(cache_path)
    
    subpath = quote(subpath, safe="/")
    full_path = os.path.join(cache_path, subpath)
    os.makedirs(os.path.dirname(full_path), exist_ok=True)

    if True:
        if subpath.startswith("bulletinList"):
            arch = request.args.get("target", None)
            if arch is None:
                arch = "Android"
            file = requests.get(f"https://ak-webview.hypergryph.com/api/game/bulletinList?target=Android", stream=True, verify=False, headers=header)
        else:
            file = requests.get(f"https://ak-webview.hypergryph.com/api/game/{subpath}", stream=True, verify=False, headers=header)
        if file.status_code == 200:
            with open(f"{cache_path}/{subpath}", "wb") as f:
                for chunk in file.iter_content(chunk_size=4096):
                    f.write(chunk)
            
    server_config = get_memory("config")
    if server_config["server"]["adaptive"]:
        server = request.host_url.rstrip("/")
    else:
        server = f"http://{server_config['server']['host']}:{server_config['server']['port']}"

    with open(full_path, "r", encoding="utf-8") as f:
        content = f.read()
    content = content.replace("https://web.hycdn.cn", server)
    # 返回响应，保留 Content-Type
    content_type = "application/json"
    return Response(content, content_type=content_type)

def announceImages(subpath):
    from urllib.parse import quote
    from flask import send_from_directory
    
    cache_path = os.path.abspath("./assets/hycdn/announce/images/")

    if not os.path.isdir(cache_path):
        os.makedirs(cache_path)
    
    subpath = quote(subpath, safe="/")
    full_path = os.path.join(cache_path, subpath)
    os.makedirs(os.path.dirname(full_path), exist_ok=True)

    if True:
        file = requests.get(f"https://web.hycdn.cn/announce/images/{subpath}", stream=True, verify=False)
        if file.status_code == 200:
            with open(f"{cache_path}/{subpath}", "wb") as f:
                for chunk in file.iter_content(chunk_size=4096):
                    f.write(chunk)
            
    return send_from_directory(cache_path, subpath)
