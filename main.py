import os
import datetime
import pytz
import requests
from bs4 import BeautifulSoup

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

def get_mlb_schedule():
    tz_tw = pytz.timezone('Asia/Taipei')
    today_tw = datetime.datetime.now(tz_tw)
    today_str = today_tw.strftime("%Y-%m-%d")
    
    url = f"https://statsapi.mlb.com/api/v1/schedule?sportId=1&date={today_str}&hydrate=team"
    
    try:
        response = requests.get(url, timeout=10).json()
        games = []
        dates = response.get('dates', [])
        
        if not dates:
            return f"🇺🇸 **MLB 今日賽事 (台灣時間 {today_str})**\n無賽事安排。"
            
        for game in dates[0].get('games', []):
            status = game['status']['detailedState']
            # 過濾季後賽未確定的預備比賽 (If Necessary)
            if game.get('ifNecessary') == 'Y' and status == 'Scheduled':
                continue

            away = game['teams']['away']['team']['name']
            home = game['teams']['home']['team']['name']
            
            # 將 UTC 時間精準轉為台灣時間
            utc_time = datetime.datetime.strptime(game['gameDate'], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=pytz.utc)
            tw_time = utc_time.astimezone(tz_tw)
            game_tw_str = tw_time.strftime("%H:%M")
            
            games.append(f"⏰ **{game_tw_str}** | {away} vs {home} ({status})")
            
        if not games:
            return f"🇺🇸 **MLB 今日賽事 (台灣時間 {today_str})**\n今日無確定的賽事安排。"

        return f"🇺🇸 **MLB 今日賽事預告 (台灣時間 {today_str})**\n\n" + "\n".join(games)
    except Exception as e:
        return f"❌ 抓取 MLB 賽事失敗: {str(e)}"

def get_npb_schedule():
    tz_tw = pytz.timezone('Asia/Taipei')
    today_tw = datetime.datetime.now(tz_tw)
    today_str = today_tw.strftime("%Y-%m-%d")
    
    url = "https://baseball.yahoo.co.jp/npb/schedule/"
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    
    try:
        res = requests.get(url, headers=headers, timeout=10)
        res.encoding = 'utf-8'
        soup = BeautifulSoup(res.text, 'html.parser')
        
        games = []
        game_blocks = soup.select('.bb-score__item')
        
        for block in game_blocks:
            teams = block.select('.bb-score__team')
            state = block.select_one('.bb-score__link') or block.select_one('.bb-score__status')
            time_tag = block.select_one('.bb-score__time')
            
            if len(teams) >= 2:
                home_team = teams[0].text.strip()
                away_team = teams[1].text.strip()
                game_status = state.text.strip() if state else "預定"
                
                # 將日本時間 (JST GMT+9) 減去 1 小時轉為台灣時間 (CST GMT+8)
                if time_tag and ":" in time_tag.text.strip():
                    jp_time_str = time_tag.text.strip()
                    jp_time = datetime.datetime.strptime(jp_time_str, "%H:%M")
                    tw_time = jp_time - datetime.timedelta(hours=1)
                    time_display = tw_time.strftime("%H:%M")
                else:
                    time_display = "時間未定/已完賽"
                    
                games.append(f"⏰ **{time_display}** | {away_team} vs {home_team} ({game_status})")
                
        if not games:
            return f"🇯🇵 **NPB 日棒今日賽事 (台灣時間 {today_str})**\n今日無賽事安排或休兵日。"
            
        return f"🇯🇵 **NPB 日棒今日賽事預告 (台灣時間 {today_str})**\n\n" + "\n".join(games)
    except Exception as e:
        return f"❌ 抓取 NPB 賽事失敗: {str(e)}"

def send_telegram_message(message):
    if not TELEGRAM_BOT_TOKEN or not CHAT_ID:
        print("❌ 錯誤：未設定 TELEGRAM_BOT_TOKEN 或 CHAT_ID")
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": message, "parse_mode": "Markdown"}
    requests.post(url, json=payload)

if __name__ == "__main__":
    mlb_msg = get_mlb_schedule()
    npb_msg = get_npb_schedule()
    
    full_message = f"☀️ **本日棒球賽事提醒（全台灣時間）**\n\n{mlb_msg}\n\n--------------------\n\n{npb_msg}"
    send_telegram_message(full_message)
