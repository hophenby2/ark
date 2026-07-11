import os
import requests
from urllib.parse import quote
from flask import (
    redirect,
    send_file,
    send_from_directory,
    Response,
    request,
)
from threading import Thread, Event, Lock

from utils import read_json, write_json, get_memory, writeLog
from asset.mods import loadMods


header = {"User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/105.0.0.0 Safari/537.36 Edg/105.0.1343.53"}
MODS_LIST = {
    "mods": [],
    "name": [],
    "path": [],
    "download": []
}


def getFile(system=None, assetsHash=None, fileName=None):
    if assetsHash is None or fileName is None or system is None:
        return "", 400

    server_config = get_memory("config")
    proxy = server_config["assets"]["downloadPeoxy"]

    # Determine version based on server mode
    version = server_config["version"][system.lower()]["resVersion"]

    # Build CDN URLs
    url = "https://ak.hycdn.cn/assetbundle/official/{}/assets/{}/{}".format(
        system, version, fileName
    )

    # Load mods when serving hot_update_list.json
    if fileName == "hot_update_list.json" and server_config["assets"]["enableMods"]:
        loaded = loadMods(
            no_validate_mod_cache=server_config["assets"]["skipModCacheValidation"]
        )
        # Mutate module-level dict to avoid global reassignment
        MODS_LIST["mods"] = loaded["mods"]
        MODS_LIST["name"] = loaded["name"]
        MODS_LIST["path"] = loaded["path"]
        MODS_LIST["download"] = loaded["download"]

    # Proxy mode: download from CDN, then serve to client (no redirect, no local caching)
    if proxy and fileName != "hot_update_list.json" and fileName not in MODS_LIST["download"]:
        # Forward client headers (e.g. Range) and relay CDN response as-is
        forward_headers = {**header}
        forward_headers["Range"] = request.headers.get("Range", "")
        resp = requests.get(url, headers=forward_headers, verify=False)
        headers = dict(resp.headers)
        # Strip transfer-encoding to let Flask handle chunking
        headers.pop("Transfer-Encoding", None)
        return Response(resp.content, status=resp.status_code, headers=headers)

    basePath = os.path.join(".", "assets", version, "redirect")

    # downloadLocally disabled: redirect client to CDN (hot_update_list and mods excluded)
    if not server_config["assets"]["downloadLocally"]:
        basePath = os.path.join(".", "assets", version)
        if fileName != "hot_update_list.json" and fileName not in MODS_LIST["download"]:
            return redirect(url, 302)

    # Ensure base directory exists
    if not os.path.isdir(basePath):
        os.makedirs(basePath)
    filePath = os.path.join(basePath, fileName)

    # Validate cached file size against hot_update_list
    wrongSize = False
    if os.path.basename(fileName) != "hot_update_list.json":
        temp_hot_update_path = os.path.join(".", "assets", version, "hot_update_list.json")
        hot_update = read_json(temp_hot_update_path)
        if os.path.exists(filePath) and hot_update:
            for pack in hot_update.get("packInfos", []):
                if pack["name"] == fileName.rsplit(".", 1)[0]:
                    wrongSize = os.path.getsize(filePath) != pack["totalSize"]
                    break

    # Substitute mod file path for modded assets
    if server_config["assets"]["enableMods"] and fileName in MODS_LIST["download"]:
        for mod, path in zip(MODS_LIST["download"], MODS_LIST["path"]):
            if fileName == mod and os.path.exists(path):
                wrongSize = False
                filePath = path
                basePath = "mods"
                fileName = os.path.basename(filePath)

    return export(url, basePath, fileName, filePath, assetsHash, wrongSize, MODS_LIST)


downloading_files = {}
downloading_files_lock = Lock()


def downloadFile(url, filePath):
    writeLog("\033[1;33mDownload {}\033[0;0m".format(os.path.basename(filePath)))
    file = requests.get(url, headers=header, stream=True, verify=False)

    with open(filePath, "wb") as f:
        for chunk in file.iter_content(chunk_size=4096):
            f.write(chunk)


def export(url, basePath, fileName, filePath, assetsHash, redownload=False, mods_list=None):
    server_config = get_memory("config")
    if mods_list is None:
        mods_list = MODS_LIST

    if os.path.basename(filePath) == "hot_update_list.json":
        if os.path.exists(filePath):
            hot_update_list = read_json(filePath)
        else:
            hot_update_list = requests.get(url, headers=header, verify=False).json()
            write_json(hot_update_list, filePath)

        abInfoList = hot_update_list["abInfos"]
        newAbInfos = []

        for abInfo in abInfoList:
            if server_config["assets"]["enableMods"]:
                hot_update_list["versionId"] = assetsHash
                if len(abInfo["hash"]) == 24:
                    abInfo["hash"] = assetsHash
                if abInfo["name"] not in mods_list["name"]:
                    newAbInfos.append(abInfo)
            else:
                newAbInfos.append(abInfo)

        if server_config["assets"]["enableMods"]:
            for mod in mods_list["mods"]:
                newAbInfos.append(mod)

        hot_update_list["abInfos"] = newAbInfos

        cachePath = "../assets/cache/"
        savePath = cachePath + "hot_update_list.json"

        if not os.path.isdir(cachePath):
            os.makedirs(cachePath)
        write_json(hot_update_list, savePath)

        return send_file("../assets/cache/hot_update_list.json")

    downloading_files_lock.acquire()
    downloading_thread = None
    if filePath in downloading_files or not os.path.exists(filePath) or redownload:
        if filePath not in downloading_files:
            downloading_files[filePath] = Event()
            downloading_thread = Thread(target=downloadFile, args=(url, filePath))
            downloading_thread.start()
        event = downloading_files[filePath]
        downloading_files_lock.release()
        if downloading_thread is not None:
            downloading_thread.join()
            event.set()
            downloading_files_lock.acquire()
            del downloading_files[filePath]
            downloading_files_lock.release()
        else:
            event.wait()
    else:
        downloading_files_lock.release()
    return send_from_directory(os.path.join("..", basePath), fileName)


def proxy_assest(subpath):
    cache_path = os.path.abspath("./assets/hycdn/arknights/")

    if not os.path.isdir(cache_path):
        os.makedirs(cache_path)
    
    subpath = quote(subpath, safe="/")
    full_path = os.path.join(cache_path, subpath)
    os.makedirs(os.path.dirname(full_path), exist_ok=True)

    if not os.path.isfile(full_path):
        file = requests.get(f"https://web.hycdn.cn/arknights/{subpath}", stream=True, verify=False, headers=header)
        if file.status_code == 200:
            with open(f"{cache_path}/{subpath}", "wb") as f:
                for chunk in file.iter_content(chunk_size=4096):
                    f.write(chunk)

    server_config = get_memory("config")
    if server_config["server"]["adaptive"]:
        server = request.host_url.rstrip("/")
    else:
        server = f"http://{server_config['server']['host']}:{server_config['server']['port']}"

    TEXT_TYPES = (".js", ".css")
    
    if subpath.endswith(TEXT_TYPES):
        with open(full_path, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()
        content = content.replace("https://web.hycdn.cn", server)
        # 返回响应，保留 Content-Type
        content_type = "application/javascript" if subpath.endswith(".js") else "text/css"
        return Response(content, content_type=content_type)

    # 二进制文件直接返回
    return send_from_directory(cache_path, subpath)
