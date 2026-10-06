import os
import datetime
import pytz
import requests

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

def get_playsport_games_next_24h(alliance_id, league_name):
    tz_tw = pytz.timezone('Asia/Taipei')
    now_tw = datetime.datetime.now(tz_tw)
    
    # 抓取今天與明天的玩運彩賽事
    today = now_tw.date()
    tomorrow = today + datetime.timedelta(days=1)
    
    target_dates = [today, tomorrow]
    valid_games = []
    
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
                game_list = data.get('games', [])
                
                for g in game_list:
                    away = g.get('away_team_name', '').strip()
                    home = g.get('home_team_name', '').strip()
                    time_str = g.get('game_time', '').strip()  # 例如 "06:00" 或 "09:30"
                    status = g.get('status_name', '預定').strip()
                    
                    if not (away and home and time_str):
                        continue
                    
                    # 解析開打時間，組合成完整的台灣時間 datetime
                    try:
                        h, m = map(int, time_str.split(':'))
                        game_datetime = tz_tw.localize(datetime.datetime(d.year, d.month, d.day, h, m))
                        
                        # 核心邏輯：只抓「發布當下」到「未來 24 小時內」的比賽
                        if now_tw <= game_datetime <= (now_tw + datetime.timedelta(hours=24)):
                            date_label = game_datetime.strftime("%m/%d")
                            valid_games.append({
                                'datetime': game_datetime,
                                'text': f"⏰ **{date_label} {time_str}** | {away} vs {home} ({status})"
                            })
                    except Exception:
                        continue
        except Exception:
            pass
            
    # 按開打時間排序
    valid_games.sort(key=lambda x: x['datetime'])
    
    if not valid_games:
        return f"⚾ **{league_name} 未來 24 小時賽事**\n未來 24 小時內無賽事安排或休兵日。"
        
    game_texts = [g['text'] for g in valid_games]
    return f"⚾ **{league_name} 未來 24 小時賽事**\n\n" + "\n".join(game_texts)

def send_telegram_message(message):
    if not TELEGRAM_BOT_TOKEN or not CHAT_ID:
        print("❌ 錯誤：未設定 TELEGRAM_BOT_TOKEN 或 CHAT_ID")
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": message, "parse_mode": "Markdown"}
    requests.post(url, json
