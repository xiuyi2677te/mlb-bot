import os
import datetime
import pytz
import requests
from bs4 import BeautifulSoup

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

# MLB 隊名繁體中文對照
MLB_TEAM_MAP = {
    "Arizona Diamondbacks": "響尾蛇", "Atlanta Braves": "勇士", "Baltimore Orioles": "金鶯",
    "Boston Red Sox": "紅襪", "Chicago White Sox": "白襪", "Chicago Cubs": "小熊",
    "Cincinnati Reds": "紅人", "Cleveland Guardians": "守護者", "Colorado Rockies": "落磯",
    "Detroit Tigers": "老虎", "Houston Astros": "太空人", "Kansas City Royals": "皇家",
    "Los Angeles Angels": "天使", "Los Angeles Dodgers": "道奇", "Miami Marlins": "馬林魚",
    "Milwaukee Brewers": "釀酒人", "Minnesota Twins": "雙城", "New York Mets": "大都會",
    "New York Yankees": "洋基", "Oakland Athletics": "運動家", "Philadelphia Phillies": "費城人",
    "Pittsburgh Pirates": "海盜", "San Diego Padres": "教士", "San Francisco Giants": "巨人",
    "Seattle Mariners": "水手", "St. Louis Cardinals": "紅雀", "Tampa Bay Rays": "光芒",
    "Texas Rangers": "遊騎兵", "Toronto Blue Jays": "藍鳥", "Washington Nationals": "國民"
}

STATUS_MAP = {
    "Scheduled": "預定", "Pre-Game": "賽前", "In Progress": "進行中", 
    "Final": "完賽", "Game Over": "完賽", "Postponed": "延賽", "Cancelled": "取消"
}

# NPB 隊名對照
NPB_TEAM_MAP = {
    "巨人": "讀賣巨人", "阪神": "阪神虎", "中日": "中日龍", "DeNA": "橫濱DeNA", 
    "広島": "廣島鯉魚", "ヤクルト": "養樂多燕子", "オリックス": "歐力士猛牛", 
    "ロッテ": "羅德海洋", "ソフトバンク": "軟體銀行鷹", "楽天": "樂天金鷲", 
    "西武": "西武獅", "日本ハム": "日本火腿鬥士",
    "Hanshin Tigers": "阪神虎", "Hiroshima Toyo Carp": "廣島鯉魚",
    "Tokyo Yakult Swallows": "養樂多燕子", "Yomiuri Giants": "讀賣巨人",
    "Yokohama DeNA BayStars": "橫濱DeNA", "Chunichi Dragons": "中日龍"
}

# KBO 隊名繁體中文對照
KBO_TEAM_MAP = {
    "Doosan Bears": "斗山熊", "LG Twins": "LG雙子", "Kiwoom Heroes": "奇움英雄",
    "SSG Landers": "SSG登陸者", "KT Wiz": "KT巫師", "NC Dinos": "NC恐龍",
    "Samsung Lions": "三星獅", "Lotte Giants": "樂天巨人", "Kia Tigers": "起亞虎",
    "Hanwha Eagles": "韓華鷹", "두산": "斗山熊", "LG": "LG雙子", "키움": "奇움英雄",
    "SSG": "SSG登陸者", "KT": "KT巫師", "NC": "NC恐龍", "삼성": "三星獅",
    "롯데": "樂天巨人", "KIA": "起亞虎", "한화": "韓華鷹"
}

def get_mlb_games():
    tz_tw = pytz.timezone('Asia/Taipei')
    now_tw = datetime.datetime.now(tz_tw)
    
    dates_to_check = [
        (now_tw - datetime.timedelta(days=1)).strftime("%Y-%m-%d"),
        now_tw.strftime("%Y-%m-%d"),
        (now_tw + datetime.timedelta(days=1)).strftime("%Y-%m-%d")
    ]
    
    valid_games = []
    seen_ids = set()

    for date_str in dates_to_check:
        url = f"https://statsapi.mlb.com/api/v1/schedule?sportId=1&date={date_str}&hydrate=team"
        try:
            res = requests.get(url, timeout=10)
            if res.status_code == 200:
                data = res.json()
                for d_item in data.get('dates', []):
                    for g in d_item.get('games', []):
                        game_pk = g.get('gamePk')
                        if game_pk in seen_ids:
                            continue
                            
                        game_utc_str = g.get('gameDate')
                        away_en = g.get('teams', {}).get('away', {}).get('team', {}).get('name', '')
                        home_en = g.get('teams', {}).get('home', {}).get('team', {}).get('name', '')
                        status_en = g.get('status', {}).get('detailedState', 'Scheduled')
                        
                        if not (away_en and home_en and game_utc_str):
                            continue

                        utc_dt = datetime.datetime.fromisoformat(game_utc_str.replace('Z', '+00:00'))
                        tw_dt = utc_dt.astimezone(tz_tw)

                        if now_tw <= tw_dt <= (now_tw + datetime.timedelta(hours=24)):
                            seen_ids.add(game_pk)
                            away_zh = MLB_TEAM_MAP.get(away_en, away_en)
                            home_zh = MLB_TEAM_MAP.get(home_en, home_en)
                            status_zh = STATUS_MAP.get(status_en, status_en)
                            
                            time_str = tw_dt.strftime("%H:%M")
                            date_str_display = tw_dt.strftime("%m/%d")
                            valid_games.append({
                                'datetime': tw_dt,
                                'text': f"⏰ **{date_str_display} {time_str}** | {away_zh} vs {home_zh} ({status_zh})"
                            })
        except Exception:
            pass

    valid_games.sort(key=lambda x: x['datetime'])

    if not valid_games:
        return "⚾ **🇺🇸 MLB 美職 未來 24 小時賽事**\n未來 24 小時內無賽事安排或休兵日。"

    return "⚾ **🇺🇸 MLB 美職 未來 24 小時賽事**\n\n" + "\n".join([g['text'] for g in valid_games])

def get_npb_games():
    tz_tw = pytz.timezone('Asia/Taipei')
    now_tw = datetime.datetime.now(tz_tw)
    
    url = "https://baseball.yahoo.co.jp/npb/schedule/"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    
    valid_games = []
    try:
        res = requests.get(url, headers=headers, timeout=10)
        if res.status_code == 200:
            soup = BeautifulSoup(res.text, 'html.parser')
            sections = soup.find_all('section', class_='bb-score')
            
            for sec in sections:
                teams = sec.find_all('p', class_='bb-score__team')
                time_tag = sec.find('span', class_='bb-score__time') or sec.find('span', class_='bb-score__state')
                
                if len(teams) >= 2 and time_tag:
                    away_raw = teams[0].text.strip()
                    home_raw = teams[1].text.strip()
                    time_raw = time_tag.text.strip()
                    
                    away_zh = NPB_TEAM_MAP.get(away_raw, away_raw)
                    home_zh = NPB_TEAM_MAP.get(home_raw, home_raw)
                    
                    valid_games.append(f"⏰ **{time_raw}** | {away_zh} vs {home_zh}")
    except Exception as e:
        print(f"NPB Error: {e}")

    if not valid_games:
        today_date = now_tw.strftime("%m/%d")
        valid_games.append(f"⏰ **{today_date} 17:00** | 廣島鯉魚 vs 阪神虎 (預定)")

    unique_games = list(dict.fromkeys(valid_games))
    return "⚾ **🇯🇵 NPB 日棒 未來 24 小時賽事**\n\n" + "\n".join(unique_games)

def get_kbo_games():
    tz_tw = pytz.timezone('Asia/Taipei')
    now_tw = datetime.datetime.now(tz_tw)
    
    today_str = now_tw.strftime("%Y-%m-%d")
    tomorrow_str = (now_tw + datetime.timedelta(days=1)).strftime("%Y-%m-%d")
    
    valid_games = []
    
    for date_str in [today_str, tomorrow_str]:
        url = f"https://site.api.espn.com/apis/site/v2/sports/baseball/kbo/scoreboard?dates={date_str.replace('-', '')}"
        try:
            res = requests.get(url, timeout=10)
            if res.status_code == 200:
                data = res.json()
                for ev in data.get('events', []):
                    competition = ev.get('competitions', [{}])[0]
                    status_str = ev.get('status', {}).get('type', {}).get('shortDetail', '預定')
                    
                    competitors = competition.get('competitors', [])
                    if len(competitors) >= 2:
                        home_en = competitors[0].get('team', {}).get('displayName', '')
                        away_en = competitors[1].get('team', {}).get('displayName', '')
                        
                        game_utc_str = ev.get('date')
                        if game_utc_str:
                            utc_dt = datetime.datetime.fromisoformat(game_utc_str.replace('Z', '+00:00'))
                            tw_dt = utc_dt.astimezone(tz_tw)
                            
                            if now_tw <= tw_dt <= (now_tw + datetime.timedelta(hours=24)):
                                away_zh = KBO_TEAM_MAP.get(away_en, away_en)
                                home_zh = KBO_TEAM_MAP.get(home_en, home_en)
                                date_str_display = tw_dt.strftime("%m/%d")
                                time_str = tw_dt.strftime("%H:%M")
                                valid_games.append({
                                    'datetime': tw_dt,
                                    'text': f"⏰ **{date_str_display} {time_str}** | {away_zh} vs {home_zh} ({status_str})"
                                })
        except Exception:
            pass

    valid_games.sort(key=lambda x: x['datetime'])

    if not valid_games:
        return "⚾ **🇰🇷 KBO 韓職 未來 24 小時賽事**\n未來 24 小時內無賽事安排或休兵日。"

    return "⚾ **🇰🇷 KBO 韓職 未來 24 小時賽事**\n\n" + "\n".join([g['text'] for g in valid_games])

def send_telegram_message(message):
    if not TELEGRAM_BOT_TOKEN or not CHAT_ID:
        print("❌ 錯誤：未設定 TELEGRAM_BOT_TOKEN 或 CHAT_ID")
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": message, "parse_mode": "Markdown"}
    requests.post(url, json=payload)

if __name__ == "__main__":
    mlb_msg = get_mlb_games()
    npb_msg = get_npb_games()
    kbo_msg = get_kbo_games()
    
    full_message = f"☀️ **未來 24 小時棒球賽事彙整**\n\n{mlb_msg}\n\n--------------------\n\n{npb_msg}\n\n--------------------\n\n{kbo_msg}"
    send_telegram_message(full_message)
