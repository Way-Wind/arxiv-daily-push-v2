"""保存待发消息，在网页部署成功后发送，并逐条记录确认成功的论文。"""
import json
import os
import time
from pathlib import Path

PENDING_FILE = Path("pending_delivery.json")


def save_pending(messages, papers, mode):
    entries = []
    for i, message in enumerate(messages):
        ids = [p["id"] for p in papers] if mode == "digest" else [papers[i]["id"]]
        entries.append({"message": message, "ids": ids})
    temp = PENDING_FILE.with_suffix(".tmp")
    temp.write_text(json.dumps(entries, ensure_ascii=False), encoding="utf-8")
    os.replace(temp, PENDING_FILE)


def send_pending(config):
    from main import _load_pushed_ids, _save_pushed_ids
    from wechat_push import WeChatPusher

    if not PENDING_FILE.exists():
        print("没有待发送消息")
        return
    entries = json.loads(PENDING_FILE.read_text(encoding="utf-8"))
    pushed = _load_pushed_ids()
    pusher = WeChatPusher(config["app_id"], config["app_secret"],
                          config["template_id"], config["user_openid"])
    for entry in entries:
        if set(entry["ids"]).issubset(pushed):
            continue
        msg = entry["message"]
        if not pusher.send_template(msg["data"], url=msg.get("url")):
            raise RuntimeError("微信消息未确认发送成功")
        pushed.update(entry["ids"])
        _save_pushed_ids(pushed)
        time.sleep(2)
    PENDING_FILE.unlink()
    print("[完成] 待发消息已发送并保存去重记录")


if __name__ == "__main__":
    from main import load_config
    send_pending(load_config()["wechat"])
