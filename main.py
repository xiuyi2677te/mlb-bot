import os
import datetime
import pytz
import requests

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

def get_playsport_games_next_24h(alliance_id, league_name):
    tz_tw = pytz.timezone('Asia/Taipei')
    now_tw = datetime.datetime.now(tz_tw)
    
    # 核心修復：一次抓「昨天、今天、明天」三天，徹底解決玩運彩半夜換日的 API 歸類盲點
    yesterday = (now_tw - datetime.timedelta(days=1)).date()
    today = now_tw.date()
    tomorrow = (now_tw + datetime.timedelta(days=1)).date()
    
    target_dates = [yesterday, today, tomorrow]
    valid_games = []
    seen_games = set()  # 用來避免重複抓取
    
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
                    
                    if not (away and home and ":" in time_str):
                        continue
                    
                    try:
                        h, m = map(int, time_str.split(':'))
                        game_datetime = tz_tw.localize(datetime.datetime(d.year, d.month, d.day, h, m))
                        
                        # 過濾條件：開打時間在「發布當下 ~ 未來 24 小時內」
                        if now_tw <= game_datetime <= (now_tw + datetime.timedelta(hours=24)):
                            game_key = f"{game_datetime.strftime('%Y%m%d%H%m')}_{away}_{home}"
                            if game_key not in seen_games:
                                seen_games.add(game_key)
                                date_label = game_datetime.strftime("%m/%d")
                                valid_games.append({
                                    'datetime': game_datetime,
                                    'text': f"⏰ **{date_label} {time_str}** | {away} vs {home} ({status})"
                                })
                    except Exception:
                        continue
        except Exception:
            pass
            
    # 按照開打時間由近到遠排序
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
    requests.post(url, json=payload)

if __name__ == "__main__":
    mlb_msg = get_playsport_games_next_24h(1, "🇺🇸 MLB 美職")
    npb_msg = get_playsport_games_next_24h(2, "🇯🇵 NPB 日棒")
    
    full_message = f"☀️ **未來 24 小時棒球賽事彙整**\n\n{mlb_msg}\n\n--------------------\n\n{npb_msg}"
    send_telegram_message(full_message)
