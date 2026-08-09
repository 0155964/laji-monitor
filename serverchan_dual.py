import os

import requests

import monitor


_original_send = monitor.send_wechat_msg
_SECOND_SEND_KEY = os.environ.get("SERVERCHAN_SENDKEY", "")


def send_dual(title, content):
    _original_send(title, content)

    if not _SECOND_SEND_KEY:
        print("未配置 SERVERCHAN_SENDKEY，跳过第二个 Server酱账号推送。")
        return

    url = f"https://sctapi.ftqq.com/{_SECOND_SEND_KEY}.send"
    try:
        response = requests.post(
            url,
            data={"title": title, "desp": content},
            timeout=10,
        )
        response.raise_for_status()
        print("第二个 Server酱账号推送成功。")
    except requests.RequestException as exc:
        print(f"第二个 Server酱账号推送失败：{exc}")


monitor.send_wechat_msg = send_dual


if __name__ == "__main__":
    monitor.monitor()
