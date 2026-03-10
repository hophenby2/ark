import json

import requests

with open("../config/config.json") as f:
    config = json.load(f)

servers = [
    ["version", "cn", "ak-conf.hypergryph.com"],
    ["versionGlobal", "global", "ak-conf.arknights.global"]
]

platforms = {
    "android": {
        "version": "https://ak-conf.hypergryph.com/config/prod/official/Android/version",
        "versionGlobal": "https://ark-us-static-online.yo-star.com/assetbundle/official/Android/version"
    },
    "Windows": {
        "version": "https://ak-conf.hypergryph.com/config/prod/official/Windows/version"
    }
}

timeout = 30
res_version_changed = False

for config_key, network_key, host in servers:
    # 更新各平台版本
    for platform in ["android", "Windows"]:
        if platform in config[config_key] and platform in platforms:
            url = platforms[platform].get(config_key)
            if url:
                try:
                    version_data = requests.get(url, timeout=timeout).json()
                    old = config[config_key][platform]
                    if version_data["resVersion"] != old["resVersion"]:
                        old["resVersion"] = version_data["resVersion"]
                        res_version_changed = True
                    if version_data["clientVersion"] != old["clientVersion"]:
                        old["clientVersion"] = version_data["clientVersion"]
                except:
                    pass

    # 更新网络配置
    try:
        network_config = requests.get(
            f"https://{host}/config/prod/official/network_config", timeout=timeout
        ).json()
        content = json.loads(network_config["content"])
        funcVer = content["funcVer"]
        old_funcVer = config["networkConfig"][network_key]["content"]["funcVer"]

        if funcVer != old_funcVer:
            old_config = config["networkConfig"][network_key]["content"]["configs"][old_funcVer]
            config["networkConfig"][network_key]["content"]["funcVer"] = funcVer
            config["networkConfig"][network_key]["content"]["configs"][funcVer] = old_config
            del config["networkConfig"][network_key]["content"]["configs"][old_funcVer]
    except:
        pass

# 如果resVersion有更新，设置useUserData为false
if res_version_changed:
    config["userConfig"]["useUserData"] = False

with open("../config/config.json", "w") as f:
    json.dump(config, f, indent=4)