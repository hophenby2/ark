from flask import request

from constants import DEPOT_PATH
from utils import read_json


def getVoucherDetail():
    request_data = request.get_json()

    item_id = request_data.get('itemId')
    inst_id = request_data.get('instId')

    voucher = read_json(f'{DEPOT_PATH}voucher.json', encoding="utf-8")
    if item_id in voucher:
        # 返回对应的voucher详情
        voucher_info = voucher[item_id]
        response = voucher_info
        return response

def voucherGacha():
    return {}, 202

def getCharGachaVoucherDetail():
    return {}, 202

def getMaterialVoucherDetail():
    return {}, 202

def useCharGachaVoucher():
    return {}, 202

def useMaterialVoucher():
    return {}, 202

def useFullPotentialItem():
    return {}, 202

def useOptionVoucher():
    return {}, 202
