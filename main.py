import os
import datetime
import pytz
import requests

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

def get_mlb_games_official():
    tz_tw = pytz.timezone('Asia/Taipei')
    now_tw = datetime.datetime.now(tz_tw)
    
    # 抓取今天與明天的 MLB 賽事
    today = now_tw.date()
    tomorrow = today + datetime.timedelta(days=1)
    
    valid_games = []
    seen_games = set()

    for d in [today, tomorrow]:
        date_str = d.strftime("%Y-%m-%d")
        url = f"https://statsapi.mlb.com/api/v1/schedule?sportId=1&date={date_str}"
        
        try:
            res = requests.get(url, timeout=10)
            if res.status_code == 200:
                data = res.json()
                dates = data.get('dates', [])
                for d_item in dates:
                    games = d_item.get('games', [])
                    for g in games:
                        game_utc_str = g.get('gameDate') # UTC時間
                        away_team = g.get('teams', {}).get('away', {}).get('team', {}).get('name', '')
                        home_team = g.get('teams', {}).get('home', {}).get('team', {}).get('name', '')
                        status_detailed = g.get('status', {}).get('detailedState', 'Scheduled')
                        
                        if not (away_team and home_team and game_utc_str):
                            continue

                        # UTC 轉 台灣時間
                        utc_dt = datetime.datetime.fromisoformat(game_utc_str.replace('Z', '+00:00'))
                        tw_dt = utc_dt.astimezone(tz_tw)

                        # 篩選條件：發布當下起算未來 24 小時內
                        if now_tw <= tw_dt <= (now_tw + datetime.timedelta(hours=24)):
                            game_key = f"{tw_dt.strftime('%Y%m%d%H%M')}_{away_team}_{home_team}"
                            if game_key not in seen_games:
                                seen_games.add(game_key)
                                date_time_label = tw_dt.strftime("%m/%d %H:%M")
                                valid_games.append({
                                    'datetime': tw_dt,
                                    'text': f"⏰ **{date_time_label}** | {away_team} vs {home_team} ({status_detailed})"
                                })
        except Exception as e:
            print(f"MLB API Error: {e}")

    valid_games.sort(key=lambda x: x['datetime'])

    if not valid_games:
        return "⚾ **🇺🇸 MLB 美職 未來 24 小時賽事**\n未來 24 小時內無賽事安排或休兵日。"

    game_texts = [g['text'] for g in valid_games]
    return "⚾ **🇺🇸 MLB 美職 未來 24 小時賽事**\n\n" + "\n".join(game_texts)

def send_telegram_message(message):
    if not TELEGRAM_BOT_TOKEN or not CHAT_ID:
        print("❌ 錯誤：未設定 TELEGRAM_BOT_TOKEN 或 CHAT_ID")
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": message, "parse_mode": "Markdown"}
    requests.post(url, json=payload)

if __name__ == "__main__":
    mlb_msg = get_mlb_games_official()
    
    full_message = f"☀️ **未來 24 小時棒球賽事彙整**\n\n{mlb_msg}"
    send_telegram_message(full_message)
