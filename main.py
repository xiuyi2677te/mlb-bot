import os
import datetime
import pytz
import requests

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

def get_playsport_games(alliance_id, league_name):
    """
    alliance_id: 1 為 MLB 美職, 2 為 NPB 日棒
    """
    tz_tw = pytz.timezone('Asia/Taipei')
    today_tw = datetime.datetime.now(tz_tw)
    today_str = today_tw.strftime("%Y-%m-%d")
    today_compact = today_tw.strftime("%Y%m%d")
    
    url = f"https://www.playsport.cc/predictgame.php?action=get_game_list&allianceid={alliance_id}&gamedate={today_compact}"
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
            return f"⚾ **{league_name} 今日賽事 ({today_str})**\n今日無賽事安排或休兵日。"
            
        return f"⚾ **{league_name} 今日賽事 ({today_str})**\n\n" + "\n".join(games)
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
    
    full_message = f"☀️ **本日棒球賽事提醒（玩運彩對齊版）**\n\n{mlb_msg}\n\n--------------------\n\n{npb_msg}"
    send_telegram_message(full_message)
