import os
import requests
from datetime import datetime
import pytz
from fastapi import FastAPI

app = FastAPI()

# 核心環境變數（從 Render Dashboard 讀取）
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_GROUP_ID = os.environ.get("TELEGRAM_GROUP_ID", "")

def get_npb_kbo_data() -> str:
    """
    ⚾ 抓取日棒/韓棒賽事邏輯區
    (這裡請替換/放入你原本在 CMD 測試成功的抓取邏輯)
    """
    now_str = datetime.now(pytz.timezone('Asia/Taipei')).strftime("%Y-%m-%d %H:%M")
    
    # 範例回傳內容：
    report = (
        f"⚾ **【山河體育】日棒 / 韓棒 賽事即時彙整**\n"
        f"🕒 更新時間：`{now_str}`\n"
        f"----------------------------------------\n"
        f"🇯🇵 日棒（NPB）：阪神虎 vs 巨人 (17:00)\n"
        f"🇰🇷 韓棒（KBO）：SSG 蘭陸者 vs 斗山熊 (17:30)\n"
        f"👉 賽事數據分析已更新！"
    )
    return report

def send_telegram_msg(text: str):
    """發送訊息至 Telegram 群組"""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_GROUP_ID:
        return {"error": "未設定 TELEGRAM_BOT_TOKEN 或 TELEGRAM_GROUP_ID"}
        
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_GROUP_ID,
        "text": text,
        "parse_mode": "Markdown"
    }
    res = requests.post(url, json=payload, timeout=10)
    return res.json()

@app.get("/")
def home():
    return {"status": "ok", "service": "山河體育 API 運作中"}

# 🎯 雲端定時觸發專用 Endpoint
@app.get("/push_telegram")
def trigger_push():
    content = get_npb_kbo_data()
    result = send_telegram_msg(content)
    return {"status": "success", "telegram_response": result}

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port)
