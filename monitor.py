#每天的晚上6-9点，如果当日积分和剩余积分有增加则今天停止运行
#如果发现当日积分增加，我们就把今天的“日期”存入 last_data.json 中作为标记。后续每次运行脚本时，先检查这个日期，如果是今天，就直接退出不查了；如果是第二天，自动恢复检查。
import requests
import urllib.parse
import os
import json
import time
import sys
from datetime import datetime, timezone, timedelta

# 从环境变量中读取敏感信息
TARGET_NAME = os.environ.get("TARGET_NAME", "")
VILLAGE_ID = os.environ.get("VILLAGE_ID", "")
SERVER_CHAN_KEY = os.environ.get("SERVER_KEY", "") 

# 增加安全检查：如果缺少任何一个必填配置，则报错退出
if not TARGET_NAME or not VILLAGE_ID:
    print("错误：未在环境变量(Secrets)中配置 TARGET_NAME 或 VILLAGE_ID，程序退出。")
    sys.exit(1)

ENCODED_USER_ID = urllib.parse.quote(TARGET_NAME)
API_URL = f"https://health.yueqixx.cn/rubbish/user/queryRanking?villageId={VILLAGE_ID}&userId={ENCODED_USER_ID}&type=0&pageNo=1&pageSize=10"

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
        
        # 核心拦截逻辑：检查今天是否已经彻底完成（拿到至少8分）
        if last_data and last_data.get("finished_date") == current_date_str:
            print(f"[{current_date_str}] 今日积分已达标，暂停运行，明天自动恢复。")
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

        # 【脱敏处理】保存到 JSON 并推送到 GitHub 的内容全部打码
        current_simplified = {
            "groupName": "***",
            "numberPlate": "***",
            "userName": "***",
            "account": account,
            "todayAccount": todayAccount,
            "ranking": ranking,
            "allAccount": allAccount,
            "usedAccount": usedAccount,
            "finished_date": last_data.get("finished_date") if last_data else "",
            "record_date": current_date_str
        }
        
        need_notify = False
        msg_title = ""
        # 微信推送里依然使用真实的 userName 和 groupName，因为这是发给你自己看的
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
            
            last_record_date = last_data.get('record_date', '')
            
            # 判断是否是新的一天
            if current_date_str != last_record_date:
                old_today = 0
            else:
                old_today = last_data.get('todayAccount', 0)
                
            # 跨天且积分为0时，静默更新不打扰
            if current_date_str != last_record_date and todayAccount == 0:
                print("检测到跨天积分重置为0，静默更新数据。")
                need_notify = False
            else:
                need_notify = True
                msg_title = f"积分变动提醒: {userName}"
                
                # 判断新增积分是否达到停止标准 (>=8)
                if todayAccount > old_today:
                    if todayAccount >= 8:
                        print("检测到今日积分达标(>=8)，打上今日免查标记！")
                        current_simplified["finished_date"] = current_date_str
                        msg_body += f"✅ **今日已获取 {todayAccount} 分，任务圆满达标，今日脚本停止运行**\n\n"
                    else:
                        print(f"今日积分增加至 {todayAccount}，但尚未达到8分，继续保持监控。")
                        msg_body += f"⚠️ **今日积分当前为 {todayAccount}，可能是部分到账，将继续监控后续变化**\n\n"
                
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
            
        # 只要有任何数据变化，立刻更新 JSON 供 GitHub Action 提交
        if last_data is None or current_simplified != last_data:
            with open(DATA_FILE, "w", encoding="utf-8") as f:
                json.dump(current_simplified, f, ensure_ascii=False, indent=4)
                
    except Exception as e:
        print(f"请求异常：{e}")

if __name__ == "__main__":
    monitor()
