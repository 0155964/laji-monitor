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

# 增加安全检查
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

def get_beijing_time_tuple():
    """返回当前的北京日期(YYYY-MM-DD)和时间(HH:MM:SS)"""
    utc_now = datetime.now(timezone.utc)
    bj_now = utc_now + timedelta(hours=8)
    return bj_now.strftime("%Y-%m-%d"), bj_now.strftime("%H:%M:%S")

def send_wechat_msg(title, content):
    if not SERVER_CHAN_KEY:
        print("未配置 SERVER_KEY，跳过微信通知。")
        return
    url = f"https://sctapi.ftqq.com/{SERVER_CHAN_KEY}.send"
    print(f"[DEBUG] 准备向 Server酱 发送请求...")
    print(f"[DEBUG] KEY 长度: {len(SERVER_CHAN_KEY)}, KEY 前缀: {SERVER_CHAN_KEY[:4]}")
    try:
        headers = {'Content-Type': 'application/x-www-form-urlencoded'}
        res = requests.post(url, data={"title": title, "desp": content}, headers=headers, timeout=10)
        print(f"[DEBUG] Server酱返回状态码: {res.status_code}")
        print(f"[DEBUG] Server酱返回内容: {res.text}")
    except Exception as e:
        print(f"[ERROR] 请求 Server酱 发生异常: {e}")

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
        current_date_str, current_time_str = get_beijing_time_tuple()
        
        # 核心拦截逻辑：检查今天是否已经彻底完成（拿到至少4分）
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

        # 【历史记录逻辑】更新：兼容旧版本并支持存储时间和分数
        history_record = last_data.get("history_record", {}) if last_data else {}
        
        # 获取今天已存的记录（如果旧版只存了数字，这里做兼容转换）
        today_record = history_record.get(current_date_str, {"score": 0, "time": current_time_str})
        if isinstance(today_record, int):
            today_record = {"score": today_record, "time": current_time_str}

        # 只有当前抓到的分数比历史高，才更新分数和对应的时间
        if todayAccount > today_record["score"]:
            today_record["score"] = todayAccount
            today_record["time"] = current_time_str
        
        history_record[current_date_str] = today_record

        # 【脱敏处理】
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
            "record_date": current_date_str,
            "history_record": history_record
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
            print("发现数据有变动！")
            last_record_date = last_data.get('record_date', '')
            
            if current_date_str != last_record_date:
                old_today = 0
            else:
                old_today = last_data.get('todayAccount', 0)
                
            old_account = last_data.get('account')

            # 【精准拦截】：只看 今日积分(todayAccount) 或 剩余积分(account) 是否有变化
            if todayAccount == old_today and account == old_account:
                print("今日积分和剩余积分均无变化（仅排名等变动），静默保存，不发通知。")
                need_notify = False
            elif current_date_str != last_record_date and todayAccount == 0:
                print("检测到跨天积分重置为0，静默更新数据，不发通知。")
                need_notify = False
            else:
                need_notify = True
                msg_title = f"积分变动提醒: {userName}"
                
                # 【门槛降低】：只要今日分数大于旧分数，并且达到 4 分及以上，就判定为达标
                if todayAccount > old_today:
                    if todayAccount >= 4:
                        print(f"检测到今日积分达标(>={todayAccount})，打上今日免查标记！")
                        current_simplified["finished_date"] = current_date_str
                        msg_body += f"✅ **今日已获取 {todayAccount} 分，任务圆满达标，今日脚本停止运行**\n\n"
                    else:
                        print(f"今日积分增加至 {todayAccount}，但尚未达到4分，继续保持监控。")
                        msg_body += f"⚠️ **今日积分当前为 {todayAccount}，可能是部分到账，将继续监控后续变化**\n\n"
                elif old_account is not None and account < old_account:
                    msg_body += f"🛍️ **检测到剩余积分减少，可能是进行了商品兑换**\n\n"
                
                old_rank = last_data.get('ranking')
                if old_rank != ranking:
                    msg_body += f"🏅 排名: {old_rank} -> {ranking} ({'上升' if ranking < old_rank else '下降'})\n"
                else:
                    msg_body += f"🏅 排名: {ranking}\n"
                    
                if old_today != todayAccount:
                    msg_body += f"📈 今日新增: {old_today} -> {todayAccount}\n"
                else:
                    msg_body += f"📈 今日新增: {todayAccount}\n"
                    
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
            
        # 发送微信逻辑
        if need_notify:
            send_wechat_msg(msg_title, msg_body)
            
        # 只要有任何数据变化，立刻更新 JSON 和 MD 供 GitHub Action 提交
        if last_data is None or current_simplified != last_data:
            # 写 JSON
            with open(DATA_FILE, "w", encoding="utf-8") as f:
                json.dump(current_simplified, f, ensure_ascii=False, indent=4)
            
            # 【写 Markdown 表格：支持时间和灵活的评分图标】
            try:
                with open("history.md", "w", encoding="utf-8") as f:
                    f.write("# 📅 每日积分获取记录\n\n")
                    f.write("| 日期 | 达标时间 | 当日最高新增积分 | 状态 |\n")
                    f.write("| :--- | :---: | :---: | :---: |\n")
                    # 按日期倒序排列
                    for date_key in sorted(history_record.keys(), reverse=True):
                        record = history_record[date_key]
                        
                        # 兼容以前只存了数字的旧数据
                        if isinstance(record, int):
                            score = record
                            rec_time = "未知"
                        else:
                            score = record.get("score", 0)
                            rec_time = record.get("time", "未知")

                        if score > 4:
                            icon = "🌟 补发达标"
                        elif score == 4:
                            icon = "✅ 达标"
                        elif score > 0:
                            icon = "⚠️ 未满"
                        else:
                            icon = "❌ 零分"
                            
                        f.write(f"| {date_key} | {rec_time} | {score} | {icon} |\n")
            except Exception as e:
                print(f"写入 Markdown 失败: {e}")
                
    except Exception as e:
        print(f"请求异常：{e}")

if __name__ == "__main__":
    monitor()
