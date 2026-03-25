from flask import request

from utils import write_json, writeLog, get_memory, run_after_response
from constants import SYNC_DATA_TEMPLATE_PATH

def adminVerify():

    config = get_memory("config")
    admin_key = config["server"]["adminKey"]
    auth_header = request.headers.get('Authorization')
    
    api_key = parts[1]
    writeLog(f"管理器验证请求，密钥：{api_key}")

    if not auth_header:
        return "", 401

    parts = auth_header.split()
    if len(parts) != 2 or parts[0].lower() != 'bearer':
        return "", 401

    if str(api_key) == str(admin_key):
        return "验证成功", 200

    return "", 403

def adminSaveUserData():

    json_body = request.get_json()

    config = get_memory("config")
    admin_key = config["server"]["adminKey"]
    auth_header = request.headers.get('Authorization')
    
    api_key = parts[1]
    writeLog(f"管理器写入请求，密钥：{api_key}")

    if not auth_header:
        return "", 401

    parts = auth_header.split()
    if len(parts) != 2 or parts[0].lower() != 'bearer':
        return "", 401
    
    if str(api_key) == str(admin_key):
        try:
            write_json(json_body, SYNC_DATA_TEMPLATE_PATH)
            return {"status": "success"}, 200
        except:
            return {"status": "error"}, 500
    else:
        return "", 403
    