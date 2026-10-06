import os
import datetime
import pytz
import requests

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

def get_playsport_games(alliance_id, league_name):
    tz_tw = pytz.timezone('Asia/Taipei')
    now_tw = datetime.datetime.now(tz_tw)
    
    # 盲點修正：如果現在是台灣時間凌晨 0 ~ 6 點，玩運彩的盤口歸類在上一天
    if now_tw.hour < 6:
        target_date = now_tw - datetime.timedelta(days=1)
    else:
        target_date = now_tw
        
    date_display = target_date.strftime("%Y-%m-%d")
    date_compact = target_date.strftime("%Y%m%d")
    
    url = f"https://www.playsport.cc/predictgame.php?action=get_game_list&allianceid={alliance_id}&gamedate={date_compact}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "X-Requested-With": "XMLHttpRequest"
    }
    
    try:
        res = requests.get(url, headers=headers, timeout=10)
        games = []
        
        if res.status_code == 200:
            data = res.json()
            game_list = data.get('games', [])
            
            for g in game_list:
                away = g.get('away_team_name', '').strip()
                home = g.get('home_team_name', '').strip()
                time_str = g.get('game_time', '').strip()
                status = g.get('status_name', '預定').strip()
                
                if away and home:
                    games.append(f"⏰ **{time_str}** | {away} vs {home} ({status})")
                    
        if not games:
            return f"⚾ **{league_name} 今日賽事 ({date_display})**\n今日無賽事安排或休兵日。"
            
        return f"⚾ **{league_name} 今日賽事 ({date_display})**\n\n" + "\n".join(games)
    except Exception as e:
        return f"❌ 抓取 {league_name} 賽事失敗: {str(e)}"

def send_telegram_message(message):
    if not TELEGRAM_BOT_TOKEN or not CHAT_ID:
        print("❌ 錯誤：未設定 TELEGRAM_BOT_TOKEN 或 CHAT_ID")
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": message, "parse_mode": "Markdown"}
    requests.post(url, json=payload)

if __name__ == "__main__":
    mlb_msg = get_playsport_games(1, "🇺🇸 MLB 美職")
    npb_msg = get_playsport_games(2, "🇯🇵 NPB 日棒")
    
    full_message = f"☀️ **本日棒球賽事提醒（全繁體中文版）**\n\n{mlb_msg}\n\n--------------------\n\n{npb_msg}"
    send_telegram_message(full_message)
