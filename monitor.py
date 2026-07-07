#每天的晚上6-9点，如果当日积分和剩余积分有增加则今天停止运行
#如果发现当日积分增加，我们就把今天的“日期”存入 last_data.json 中作为标记。后续每次运行脚本时，先检查这个日期，如果是今天，就直接退出不查了；如果是第二天，自动恢复检查。
import requests
import urllib.parse
import os
import json
import time
from datetime import datetime, timezone, timedelta

TARGET_NAME = "潘条珍" 
SERVER_CHAN_KEY = os.environ.get("SERVER_KEY", "") 

ENCODED_USER_ID = urllib.parse.quote(TARGET_NAME)
API_URL = f"https://health.yueqixx.cn/rubbish/user/queryRanking?villageId=10126&userId={ENCODED_USER_ID}&type=0&pageNo=1&pageSize=10"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
    "Accept": "application/json, text/plain, */*",
    "Referer": "http://rubbish.yueqixx.cn:8912/"
}

DATA_FILE = "last_data.json"

def get_beijing_date():
    """获取当前的北京时间日期 (YYYY-MM-DD)"""
    utc_now = datetime.now(timezone.utc)
    bj_now = utc_now + timedelta(hours=8)
    return bj_now.strftime("%Y-%m-%d")

def send_wechat_msg(title, content):
    if not SERVER_CHAN_KEY:
        print("未配置 SERVER_KEY，跳过微信通知。")
        return
    url = f"https://sctapi.ftqq.com/{SERVER_CHAN_KEY}.send"
    requests.post(url, data={"title": title, "desp": content})

def get_last_data():
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return None

def monitor():
    try:
        last_data = get_last_data()
        current_date_str = get_beijing_date()
        
        # 核心拦截逻辑：检查今天是否已经收到过增加的积分了
        if last_data and last_data.get("finished_date") == current_date_str:
            print(f"[{current_date_str}] 今日积分已获取，暂停运行，明天自动恢复。")
            return

        timestamp = int(time.time() * 1000)
        no_cache_url = f"{API_URL}&_t={timestamp}"
        
        response = requests.get(no_cache_url, headers=HEADERS, timeout=10)
        data = response.json()
        search_result_list = data.get("data", {}).get("searchResult", [])
        
        if not search_result_list:
            print("未找到目标数据")
            return
            
        current = search_result_list[0]
        
        groupName = current.get('groupName')
        numberPlate = current.get('numberPlate')
        userName = current.get('userName')
        account = current.get('account')
        todayAccount = current.get('todayAccount')
        ranking = current.get('ranking')
        allAccount = current.get('allAccount')
        usedAccount = current.get('usedAccount')

        current_simplified = {
            "groupName": groupName,
            "numberPlate": numberPlate,
            "userName": userName,
            "account": account,
            "todayAccount": todayAccount,
            "ranking": ranking,
            "allAccount": allAccount,
            "usedAccount": usedAccount,
            "finished_date": last_data.get("finished_date") if last_data else "" # 默认继承旧的完成日期
        }
        
        need_notify = False
        msg_title = ""
        msg_body = f"👤 姓名: {userName}\n🏠 地址: {groupName} {numberPlate}\n\n"
        
        if last_data is None:
            print("初次运行，建立初始记录。")
            need_notify = True
            msg_title = f"开始监控: {userName}"
            msg_body += (
                f"当前排名: {ranking}\n"
                f"今日新增: {todayAccount}\n"
                f"剩余积分: {account}\n"
                f"历史总分: {allAccount}\n"
                f"已用积分: {usedAccount}"
            )
            
        elif current_simplified != last_data:
            print("发现积分或排名变化！")
            need_notify = True
            msg_title = f"积分变动提醒: {userName}"
            
            # 判断逻辑：如果今日新增积分变多了，说明今天的分已经拿到了
            # 给 current_simplified 打上“今天已完成”的标记
            old_today = last_data.get('todayAccount', 0)
            if todayAccount > old_today:
                print("检测到今日积分增加，打上今日免查标记！")
                current_simplified["finished_date"] = current_date_str
                msg_body += f"✅ **今日任务已达标，今日脚本停止运行，明早自动恢复**\n\n"
            
            old_rank = last_data.get('ranking')
            if old_rank != ranking:
                msg_body += f"🏅 排名: {old_rank} -> {ranking} ({'上升' if ranking < old_rank else '下降'})\n"
            else:
                msg_body += f"🏅 排名: {ranking}\n"
                
            if old_today != todayAccount:
                msg_body += f"📈 今日新增: {old_today} -> {todayAccount}\n"
            else:
                msg_body += f"📈 今日新增: {todayAccount}\n"
                
            old_account = last_data.get('account')
            if old_account != account:
                diff = account - old_account if old_account is not None else 0
                sign = f"+{diff}" if diff > 0 else f"{diff}"
                msg_body += f"💰 剩余积分: {old_account} -> {account} ({sign})\n"
            else:
                msg_body += f"💰 剩余积分: {account}\n"
                
            old_total = last_data.get('allAccount')
            if old_total != allAccount:
                diff = allAccount - old_total if old_total is not None else 0
                sign = f"+{diff}" if diff > 0 else f"{diff}"
                msg_body += f"🌟 历史总分: {old_total} -> {allAccount} ({sign})\n"
            else:
                msg_body += f"🌟 历史总分: {allAccount}\n"
                
            old_used = last_data.get('usedAccount')
            if old_used != usedAccount:
                diff = usedAccount - old_used if old_used is not None else 0
                sign = f"+{diff}" if diff > 0 else f"{diff}"
                msg_body += f"🛒 已用积分: {old_used} -> {usedAccount} ({sign})\n"
            else:
                msg_body += f"🛒 已用积分: {usedAccount}\n"
                
        else:
            print(f"数据未发生变化。剩余积分维持 {account}。")
            
        if need_notify:
            send_wechat_msg(msg_title, msg_body)
            with open(DATA_FILE, "w", encoding="utf-8") as f:
                json.dump(current_simplified, f, ensure_ascii=False, indent=4)
                
    except Exception as e:
        print(f"请求异常：{e}")

if __name__ == "__main__":
    monitor()


#monitor.py
