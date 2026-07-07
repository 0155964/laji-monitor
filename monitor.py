import requests
import urllib.parse
import os
import json

TARGET_NAME = "潘条珍" 
SERVER_CHAN_KEY = os.environ.get("SERVER_KEY", "") 

ENCODED_USER_ID = urllib.parse.quote(TARGET_NAME)
API_URL = f"https://health.yueqixx.cn/rubbish/user/queryRanking?villageId=10126&userId={ENCODED_USER_ID}&type=0&pageNo=1&pageSize=10"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
    "Accept": "application/json, text/plain, */*",
    "Referer": "http://rubbish.yueqixx.cn:8912/"
}

# 数据文件保存在当前目录下
DATA_FILE = "last_data.json"

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
        response = requests.get(API_URL, headers=HEADERS, timeout=10)
        data = response.json()
        search_result_list = data.get("data", {}).get("searchResult", [])
        
        if not search_result_list:
            print("未找到目标数据")
            return
            
        current = search_result_list[0]
        ranking = current.get('ranking')
        today = current.get('todayAccount')
        total = current.get('allAccount')
        
        current_simplified = {
            "ranking": ranking,
            "todayAccount": today,
            "allAccount": total
        }
        
        last_data = get_last_data()
        
        # 决定是否需要通知和更新文件
        need_notify = False
        msg_title = ""
        msg_body = f"姓名: {TARGET_NAME}\n\n"
        
        if last_data is None:
            # 第一次运行
            print("初次运行，建立初始记录。")
            need_notify = True
            msg_title = f"开始监控: {TARGET_NAME}"
            msg_body += f"当前排名: {ranking}\n今日新增: {today}\n总积分: {total}"
            
        elif current_simplified != last_data:
            # 发现数据不一致（无论是增还是减）
            print("发现积分或排名变化！")
            need_notify = True
            msg_title = f"积分变动提醒: {TARGET_NAME}"
            
            # 对比排名
            old_rank = last_data.get('ranking')
            if old_rank != ranking:
                msg_body += f"🏅 排名: {old_rank} -> {ranking} ({'上升' if ranking < old_rank else '下降'})\n"
            else:
                msg_body += f"🏅 排名: {ranking}\n"
                
            # 对比今日积分
            old_today = last_data.get('todayAccount')
            if old_today != today:
                msg_body += f"📈 今日积分: {old_today} -> {today}\n"
            else:
                msg_body += f"📈 今日积分: {today}\n"
                
            # 对比总积分
            old_total = last_data.get('allAccount')
            if old_total != total:
                # 判断是增加还是减少
                diff = total - old_total
                sign = f"+{diff}" if diff > 0 else f"{diff}"
                msg_body += f"🌟 总积分: {old_total} -> {total} ({sign})\n"
            else:
                msg_body += f"🌟 总积分: {total}\n"
        else:
            print(f"数据未发生变化。总积分维持 {total}。")
            
        # 如果需要通知，则发送微信并保存新数据
        if need_notify:
            send_wechat_msg(msg_title, msg_body)
            with open(DATA_FILE, "w", encoding="utf-8") as f:
                json.dump(current_simplified, f, ensure_ascii=False)
                
    except Exception as e:
        print(f"请求异常：{e}")

if __name__ == "__main__":
    monitor()
