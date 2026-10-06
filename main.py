import os
import datetime
import pytz
import requests
from bs4 import BeautifulSoup

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

def get_playsport_games_html(alliance_id, league_name):
    tz_tw = pytz.timezone('Asia/Taipei')
    now_tw = datetime.datetime.now(tz_tw)
    
    # 玩運彩網頁預測頁面 URL
    url = f"https://www.playsport.cc/predictgame.php?allianceid={alliance_id}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    
    games = []
    try:
        res = requests.get(url, headers=headers, timeout=10)
        if res.status_code == 200:
            soup = BeautifulSoup(res.text, 'html.parser')
            # 抓取對戰組合表格中的隊伍與時間
            rows = soup.find_all('tr', class_='game-row') or soup.find_all('tr')
            
            for row in rows:
                teams = row.find_all('td', class_='td-team-name')
                time_td = row.find('td', class_='td-game-time')
                
                if len(teams) >= 2 and time_td:
                    away = teams[0].text.strip()
                    home = teams[1].text.strip()
                    gtime = time_td.text.strip()
                    if away and home:
                        games.append(f"⏰ **{gtime}** | {away} vs {home}")
                        
        # 如果爬蟲 HTML 沒有拿到，備用 API 備援方案
        if not games:
            date_compact = now_tw.strftime("%Y%m%d")
            api_url = f"https://www.playsport.cc/predictgame.php?action=get_game_list&allianceid={alliance_id}&gamedate={date_compact}"
            api_res = requests.get(api_url, headers=headers, timeout=10)
            if api_res.status_code == 200:
                data = api_res.json()
                game_list = data.get('games', []) or []
                for g in game_list:
                    away = str(g.get('away_team_name', '')).strip()
                    home = str(g.get('home_team_name', '')).strip()
                    time_str = str(g.get('game_time', '')).strip()
                    status = str(g.get('status_name', '預定')).strip()
                    if away and home:
                        games.append(f"⏰ **{time_str}** | {away} vs {home} ({status})")

    except Exception as e:
        print(f"Fetch Error: {e}")
        
    if not games:
        return f"⚾ **{league_name} 最新賽事安排**\n今日玩運彩無賽事開盤或全數休兵。"
        
    # 去重
    unique_games = list(dict.fromkeys(games))
    return f"⚾ **{league_name} 最新賽事預告**\n\n" + "\n".join(unique_games)

def send_telegram_message(message):
    if not TELEGRAM_BOT_TOKEN or not CHAT_ID:
        print("❌ 錯誤：未設定 TELEGRAM_BOT_TOKEN 或 CHAT_ID")
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": message, "parse_mode": "Markdown"}
    requests.post(url, json=payload)

if __name__ == "__main__":
    mlb_msg = get_playsport_games_html(1, "🇺🇸 MLB 美職")
    npb_msg = get_playsport_games_html(2, "🇯🇵 NPB 日棒")
    
    full_message = f"☀️ **本日棒球賽事提醒**\n\n{mlb_msg}\n\n--------------------\n\n{npb_msg}"
    send_telegram_message(full_message)
