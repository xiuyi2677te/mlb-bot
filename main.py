import os
import datetime
import pytz
import requests

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

def get_playsport_games(alliance_id, league_name):
    tz_tw = pytz.timezone('Asia/Taipei')
    now_tw = datetime.datetime.now(tz_tw)
    
    # 半夜0-6點時，玩運彩主頁面主要呈現的是當天的盤口，抓今天與明天兩天
    today = now_tw.date()
    tomorrow = today + datetime.timedelta(days=1)
    
    # 只要現在是凌晨 6 點前，我們同時查詢今天與昨天/明天的對應頁面
    target_dates = [today]
    if now_tw.hour < 6:
        yesterday = today - datetime.timedelta(days=1)
        target_dates = [yesterday, today]
    else:
        target_dates = [today, tomorrow]
        
    valid_games = []
    seen_games = set()
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "X-Requested-With": "XMLHttpRequest"
    }
    
    for d in target_dates:
        date_compact = d.strftime("%Y%m%d")
        url = f"https://www.playsport.cc/predictgame.php?action=get_game_list&allianceid={alliance_id}&gamedate={date_compact}"
        
        try:
            res = requests.get(url, headers=headers, timeout=10)
            if res.status_code == 200:
                data = res.json()
                game_list = data.get('games', []) or []
                
                for g in game_list:
                    away = str(g.get('away_team_name', '')).strip()
                    home = str(g.get('home_team_name', '')).strip()
                    time_str = str(g.get('game_time', '')).strip()
                    status = str(g.get('status_name', '預定')).strip()
                    
                    if not (away and home and time_str):
                        continue
                    
                    # 避免跨日分頁重複顯示同場賽事
                    game_key = f"{away}_vs_{home}_{time_str}"
                    if game_key not in seen_games:
                        seen_games.add(game_key)
                        valid_games.append(f"⏰ **{time_str}** | {away} vs {home} ({status})")
        except Exception:
            pass
            
    if not valid_games:
        return f"⚾ **{league_name} 今日賽事安排**\n無賽事安排或休兵日。"
        
    return f"⚾ **{league_name} 最新賽事預告**\n\n" + "\n".join(valid_games)

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
    
    full_message = f"☀️️ **本日棒球賽事提醒**\n\n{mlb_msg}\n\n--------------------\n\n{npb_msg}"
    send_telegram_message(full_message)
