import os
import datetime
import pytz
import requests
from apscheduler.schedulers.blocking import BlockingScheduler

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

def get_mlb_schedule():
    tz_tw = pytz.timezone('Asia/Taipei')
    today_str = datetime.datetime.now(tz_tw).strftime("%Y-%m-%d")
    url = f"https://statsapi.mlb.com/api/v1/schedule?sportId=1&date={today_str}"
    
    try:
        response = requests.get(url, timeout=10).json()
        games = []
        dates = response.get('dates', [])
        
        if not dates:
            return "⚾ 今日無 MLB 賽事安排。"
            
        for game in dates[0].get('games', []):
            away = game['teams']['away']['team']['name']
            home = game['teams']['home']['team']['name']
            game_utc = datetime.datetime.fromisoformat(game['gameDate'].replace('Z', '+00:00'))
            game_tw = game_utc.astimezone(tz_tw).strftime("%H:%M")
            status = game['status']['detailedState']
            games.append(f"⏰ **{game_tw}** | {away} vs {home} ({status})")
            
        return f"📅 **MLB 今日賽事預告 ({today_str})**\n\n" + "\n".join(games)
    except Exception as e:
        return f"❌ 抓取賽事資料失敗: {str(e)}"

def send_telegram_message(message):
    if not TELEGRAM_BOT_TOKEN or not CHAT_ID:
        print("❌ 錯誤：未設定 TELEGRAM_BOT_TOKEN 或 CHAT_ID")
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": message, "parse_mode": "Markdown"}
    requests.post(url, json=payload)

def daily_job():
    mlb_msg = get_mlb_schedule()
    full_message = f"☀️ **本日棒球賽事提醒**\n\n{mlb_msg}"
    send_telegram_message(full_message)

if __name__ == "__main__":
    print("🤖 服務啟動，發送測試訊息...")
    daily_job()
    
    scheduler = BlockingScheduler(timezone="Asia/Taipei")
    scheduler.add_job(daily_job, 'cron', hour=8, minute=0)
    print("⏰ 排程已啟動，將於每日 08:00 自動推播。")
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        pass
