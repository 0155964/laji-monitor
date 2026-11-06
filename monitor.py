import json
import os
import sys
import time
import urllib.parse
from copy import deepcopy
from datetime import datetime, timezone, timedelta

import requests

TARGET_NAME = os.environ.get("TARGET_NAME", "")
VILLAGE_ID = os.environ.get("VILLAGE_ID", "")
SERVER_CHAN_KEY = os.environ.get("SERVER_KEY", "")
if not TARGET_NAME or not VILLAGE_ID:
    print("错误：未配置 TARGET_NAME 或 VILLAGE_ID。")
    sys.exit(1)

ENCODED_USER_ID = urllib.parse.quote(TARGET_NAME)
API_URL = f"https://health.yueqixx.cn/rubbish/user/queryRanking?villageId={VILLAGE_ID}&userId={ENCODED_USER_ID}&type=0&pageNo=1&pageSize=10"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
    "Accept": "application/json, text/plain, */*",
    "Referer": "http://rubbish.yueqixx.cn:8912/",
}
DATA_FILE = "last_data.json"


def get_beijing_time_tuple():
    now = datetime.now(timezone.utc) + timedelta(hours=8)
    return now.strftime("%Y-%m-%d"), now.strftime("%H:%M:%S")


def send_wechat_msg(title, content):
    if not SERVER_CHAN_KEY:
        print("未配置 SERVER_KEY，跳过微信通知。")
        return
    try:
        res = requests.post(
            f"https://sctapi.ftqq.com/{SERVER_CHAN_KEY}.send",
            data={"title": title, "desp": content}, timeout=10,
        )
        print(f"Server酱返回状态码: {res.status_code}")
        print(f"Server酱返回内容: {res.text}")
    except requests.RequestException:
        print("Server酱请求失败，请检查网络或服务状态。")


def get_last_data():
    if not os.path.exists(DATA_FILE):
        return None
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def total_delta_for(history, date_key, total):
    previous_date = (
        datetime.strptime(date_key, "%Y-%m-%d") - timedelta(days=1)
    ).strftime("%Y-%m-%d")
    previous = history.get(previous_date)
    if not isinstance(previous, dict):
        return None
    baseline = previous.get("allAccount")
    if baseline is None or total is None:
        return None
    return total - baseline


def format_delta(value):
    return "—" if value is None else f"{value:+d}"


def render_history(history):
    lines = [
        "# 每日积分获取记录", "",
        "> 运行时间保持北京时间18:00–21:55，每5分钟计划检测一次，并非实时更新；实际执行可能延迟。当天接口积分达到4分后停止查询，次日恢复。", "",
        "> 检测时间：首次建立当天记录时设置，之后仅在接口当日积分创新高时更新，不代表最后查询时间。", "",
        "> 当日最高新增积分：接口 todayAccount 当天实际检测到的最高值；0仅表示未检测到非零当日积分，不代表当天实际未得分。", "",
        "> 总分增量 = 本日最后一次成功查询并保存的历史总分 − 前一自然日最后一次保存的历史总分。表示两个快照之间的净变化，可能含此前日期补发或人工调整，不等于当天投放所得；与当日最高新增积分分开统计，不相加。前一天缺少有效总分时显示“—”，不跨缺失日期计算。负值表示总分减少，需核对。", "",
        "> 剩余积分、历史总分和已用积分均为当日最后保存的快照；达标后不再查询，因此不是日终最终值。旧记录缺少的字段显示“—”，不自动回填。", "",
        "| 日期 | 检测时间 | 当日最高新增积分 | 总分增量 | 剩余积分 | 历史总分 | 已用积分 | 状态 |",
        "| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :--- |",
    ]
    for date_key in sorted(history, reverse=True):
        record = history[date_key]
        if isinstance(record, int):
            record = {"score": record}
        score = record.get("score", 0)
        delta = total_delta_for(history, date_key, record.get("allAccount"))
        if score > 4:
            status = "达标（含额外积分，可能补发）"
        elif score == 4:
            status = "达标"
        elif score > 0:
            status = "未满4分"
        else:
            status = "暂未检测到当日积分"
        if delta is not None and delta < 0:
            status += "；总分减少待核对"
        elif score == 0 and delta is not None and delta > 0:
            status += "；总分有增加"
        cells = [date_key, record.get("time", "未知"), score,
                 format_delta(delta), record.get("account", "—"),
                 record.get("allAccount", "—"), record.get("usedAccount", "—"), status]
        lines.append("| " + " | ".join(map(str, cells)) + " |")
    return "\n".join(lines) + "\n"


def monitor():
    try:
        last_data = get_last_data()
        date_str, time_str = get_beijing_time_tuple()
        if last_data and last_data.get("finished_date") == date_str:
            print(f"[{date_str}] 今日积分已达标，暂停查询，明天恢复。")
            return

        response = requests.get(
            f"{API_URL}&_t={int(time.time() * 1000)}",
            headers=HEADERS, timeout=10,
        )
        response.raise_for_status()
        payload = response.json()
        if payload.get("code") != 200:
            print("接口返回失败，不更新已有记录。")
            return
        results = (payload.get("data") or {}).get("searchResult", [])
        matches = [item for item in results if item.get("userName") == TARGET_NAME]
        if len(matches) != 1:
            print("未找到唯一同名目标，不更新记录。")
            return
        current = matches[0]
        fields = ("todayAccount", "account", "allAccount", "usedAccount", "ranking")
        values = {key: int(current[key]) for key in fields}
        today = values["todayAccount"]
        total = values["allAccount"]
        history = deepcopy((last_data or {}).get("history_record", {}))
        record = history.get(date_str, {"score": 0, "time": time_str})
        if isinstance(record, int):
            record = {"score": record, "time": time_str}
        if today > record.get("score", 0):
            record["score"] = today
            record["time"] = time_str
        for key in ("account", "allAccount", "usedAccount"):
            record[key] = values[key]
        record["total_delta"] = total_delta_for(history, date_str, total)
        history[date_str] = record

        saved = {
            "groupName": "***", "numberPlate": "***", "userName": "***",
            **values,
            "finished_date": date_str if today >= 4 else (last_data or {}).get("finished_date", ""),
            "record_date": date_str,
            "history_record": history,
        }
        same_day = last_data is not None and last_data.get("record_date") == date_str
        today_changed = (
            today != last_data.get("todayAccount", 0)
            if same_day else today > 0
        )
        notify = last_data is None or today_changed or any(
            values[key] != last_data.get(key)
            for key in ("account", "allAccount")
        )
        if notify:
            title = f"{'开始监控' if last_data is None else '积分变动提醒'}: {current.get('userName')}"
            body = [
                f"姓名: {current.get('userName')}",
                f"地址: {current.get('groupName')} {current.get('numberPlate')}",
                f"查询时间: {date_str} {time_str}", "",
            ]
            for key, label in (("todayAccount", "当日积分"), ("account", "剩余积分"),
                               ("allAccount", "历史总分"), ("usedAccount", "已用积分"),
                               ("ranking", "排名")):
                old = (last_data or {}).get(key)
                if old is not None and old != values[key]:
                    note = "（跨天值，仅展示，不因清零单独通知）" if key == "todayAccount" and not same_day else ""
                    body.append(f"{label}: {old} -> {values[key]}{note}")
                else:
                    body.append(f"{label}: {values[key]}")
            if last_data is not None and last_data.get("allAccount") is not None:
                body.append(f"相比上次查询总分净变化: {format_delta(total - last_data['allAccount'])}")
            body.append(f"相比前一自然日已保存总分快照: {format_delta(record['total_delta'])}")
            body.append("总分差额可能含此前日期补发或人工调整，不等同于当天投放所得。")
            if today >= 4:
                body.append("当日接口积分已达4分，本次保存后停止当天查询。")
            else:
                body.append("当日接口积分未满4分，继续原时段检测。")
            send_wechat_msg(title, "\n\n".join(body))
        else:
            print("无需要通知的积分变化。")

        if saved != last_data:
            with open(DATA_FILE, "w", encoding="utf-8") as f:
                json.dump(saved, f, ensure_ascii=False, indent=4)
        markdown = render_history(history)
        previous_md = None
        if os.path.exists("history.md"):
            with open("history.md", "r", encoding="utf-8") as f:
                previous_md = f.read()
        if markdown != previous_md:
            with open("history.md", "w", encoding="utf-8") as f:
                f.write(markdown)
    except Exception as exc:
        print(f"监控失败，不清空已有历史。异常类型: {type(exc).__name__}")
        raise RuntimeError("监控失败，请检查接口、数据格式或文件状态。") from None


if __name__ == "__main__":
    monitor()
