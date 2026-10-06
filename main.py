from fastapi import FastAPI, Response
import urllib.request
import json
import re
import datetime
import ssl
import os
import requests

app = FastAPI(title="Baseball Schedule Bot API")

# 建立忽略 SSL 憑證檢查 Context
ssl_ctx = ssl._create_unverified_context()

# 設定台灣時區 (UTC+8) 與 韓國/日本時區 (UTC+9)
tz_tw = datetime.timezone(datetime.timedelta(hours=8))
tz_kr = datetime.timezone(datetime.timedelta(hours=9))

# 精簡版隊伍中文對照表
MLB_MAP = {
    "Los Angeles Dodgers": "道奇", "Atlanta Braves": "勇士",
    "Milwaukee Brewers": "釀酒人", "San Diego Padres": "教士",
    "Cleveland Guardians": "守護者", "Chicago White Sox": "白襪",
    "New York Yankees": "洋基", "Boston Red Sox": "紅襪",
    "Houston Astros": "太空人", "Philadelphia Phillies": "費城人"
}

NPB_MAP = {
    "阪神": "阪神虎", "広島": "廣島鯉魚", "巨人": "讀賣巨人", "DeNA": "橫濱",
    "中日": "中日龍", "ヤクルト": "養樂多", "ソフトバンク": "軟銀鷹",
    "ロッテ": "羅德海洋", "オリックス": "歐力士", "楽天": "樂天金鷲",
    "西武": "西武獅", "日本ハム": "日本火腿"
}

KBO_MAP = {
    "LG": "LG雙子", "두산": "斗山熊", "SSG": "SSG蘭德斯", "NC": "NC恐龍",
    "키움": "培證英雄", "한화": "韓華鷹", "롯데": "樂天巨人", "KIA": "起亞虎",
    "KT": "KT巫師", "삼성": "三星獅"
}

# 讀取 Render Dashboard 設定的環境變數
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_GROUP_ID = os.environ.get("TELEGRAM_GROUP_ID", "")

def build_schedule_text() -> str:
    """完整賽事資料抓取與排程文字生成邏輯"""
    now_tw = datetime.datetime.now(tz_tw)
    lines = ["☀️ 未來 24 小時棒球賽事彙整\n"]

    # ----------------------------------------------------
    # [1] MLB 美職
    # ----------------------------------------------------
    lines.append("⚾ 🇺🇸 MLB 美職")
    try:
        start_d = (now_tw - datetime.timedelta(days=1)).strftime("%Y-%m-%d")
        end_d = (now_tw + datetime.timedelta(days=1)).strftime("%Y-%m-%d")
        url_mlb = f"https://statsapi.mlb.com/api/v1/schedule?sportId=1&startDate={start_d}&endDate={end_d}"
        
        req = urllib.request.Request(url_mlb, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, context=ssl_ctx, timeout=10) as resp:
            data = json.loads(resp.read().decode('utf-8'))
            count = 0
            for date_item in data.get('dates', []):
                for game in date_item.get('games', []):
                    utc_str = game.get('gameDate')
                    if not utc_str: continue
                    utc_dt = datetime.datetime.fromisoformat(utc_str.replace('Z', '+00:00'))
                    tw_dt = utc_dt.astimezone(tz_tw)
                    
                    if now_tw <= tw_dt <= (now_tw + datetime.timedelta(hours=24)):
                        away_raw = game.get('teams', {}).get('away', {}).get('team', {}).get('name', '未知')
                        home_raw = game.get('teams', {}).get('home', {}).get('team', {}).get('name', '未知')
                        away = MLB_MAP.get(away_raw, away_raw)
                        home = MLB_MAP.get(home_raw, home_raw)
                        lines.append(f"{tw_dt.strftime('%m/%d %H:%M')} ⏰ {away} vs {home}")
                        count += 1
            if count == 0:
                lines.append("24 小時內無賽事")
    except Exception as e:
        lines.append(f"⚠️ 數據連線異常: {e}")

    lines.append("\n──────────────\n")

    # ----------------------------------------------------
    # [2] NPB 日棒
    # ----------------------------------------------------
    lines.append("⚾ 🇯🇵 NPB 日棒")
    npb_success = False
    npb_fetched = False
    last_err = None

    today_hyphen = now_tw.strftime("%Y-%m-%d")
    urls_to_try = [
        f"https://baseball.yahoo.co.jp/npb/schedule/?date={today_hyphen}",
        "https://baseball.yahoo.co.jp/npb/schedule/"
    ]

    headers_npb = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
        'Accept-Language': 'ja,en-US;q=0.9,en;q=0.8'
    }

    for url_npb in urls_to_try:
        if npb_success:
            break
        try:
            req = urllib.request.Request(url_npb, headers=headers_npb)
            with urllib.request.urlopen(req, context=ssl_ctx, timeout=10) as resp:
                html = resp.read().decode('utf-8')
                npb_fetched = True
                
                json_match = re.search(r'window\.__PRELOADED_STATE__\s*=\s*({[\s\S]*?});</script>', html)
                if json_match:
                    try:
                        js_data = json.loads(json_match.group(1))
                        schedule = js_data.get('schedule', {})
                        games = schedule.get('games', []) or js_data.get('games', [])
                        
                        count = 0
                        for g in games:
                            away_raw = g.get('awayTeam', {}).get('name') or g.get('away', '')
                            home_raw = g.get('homeTeam', {}).get('name') or g.get('home', '')
                            if away_raw and home_raw:
                                time_raw = g.get('startTime', '18:00')
                                hh = int(time_raw.split(':')[0]) - 1 if ':' in time_raw else 17
                                mm = time_raw.split(':')[1] if ':' in time_raw else "00"
                                tw_time = f"{now_tw.strftime('%m/%d')} {hh:02d}:{mm}"
                                away = NPB_MAP.get(away_raw, away_raw)
                                home = NPB_MAP.get(home_raw, home_raw)
                                lines.append(f"{tw_time} ⏰ {away} vs {home}")
                                count += 1
                        if count > 0:
                            npb_success = True
                            break
                    except Exception:
                        pass

                cards = re.findall(r'class="bb-score__item"[\s\S]*?</section>', html) or \
                        re.findall(r'<div class="bb-score__content">[\s\S]*?</div>\s*</div>', html) or \
                        re.findall(r'<tr class="bb-calendarTable__row">[\s\S]*?</tr>', html)
                
                count = 0
                for card in cards:
                    found_teams = []
                    for team_key in NPB_MAP.keys():
                        if team_key in card and NPB_MAP[team_key] not in found_teams:
                            found_teams.append(NPB_MAP[team_key])
                    
                    if len(found_teams) == 2:
                        time_match = re.search(r'(\d{1,2}:\d{2})', card)
                        jst_time = time_match.group(1) if time_match else "18:00"
                        hh = int(jst_time.split(':')[0]) - 1
                        mm = jst_time.split(':')[1]
                        tw_time = f"{now_tw.strftime('%m/%d')} {hh:02d}:{mm}"
                        
                        lines.append(f"{tw_time} ⏰ {found_teams[0]} vs {found_teams[1]}")
                        count += 1
                        
                if count > 0:
                    npb_success = True
                    break
        except Exception as e:
            last_err = e
            continue

    if not npb_success:
        if npb_fetched:
            lines.append("24 小時內無賽事")
        else:
            lines.append(f"⚠️ 數據連線異常: {last_err}")

    lines.append("\n──────────────\n")

    # ----------------------------------------------------
    # [3] KBO 韓職
    # ----------------------------------------------------
    lines.append("⚾ 🇰🇷 KBO 韓職")
    try:
        today_kr = now_tw.strftime("%Y-%m-%d")
        url_kbo = f"https://api-gw.sports.naver.com/schedule/games?upperCategoryId=kbaseball&fromDate={today_kr}&toDate={today_kr}"
        headers_kbo = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
            'Referer': 'https://sports.news.naver.com/',
            'Accept': 'application/json, text/plain, */*'
        }
        req = urllib.request.Request(url_kbo, headers=headers_kbo)
        
        with urllib.request.urlopen(req, context=ssl_ctx, timeout=10) as resp:
            res_text = resp.read().decode('utf-8')
            data = json.loads(res_text)
            
            result = data.get('result', {})
            games = result.get('games', []) or data.get('games', []) or []
            count = 0
            for g in games:
                away_raw = g.get('awayTeamName')
                home_raw = g.get('homeTeamName')
                
                if not away_raw or not home_raw:
                    continue
                    
                kst_time_str = g.get('gameStartTime') or g.get('startTime') or "18:30"
                
                try:
                    kr_dt = datetime.datetime.strptime(f"{today_kr} {kst_time_str}", "%Y-%m-%d %H:%M").replace(tzinfo=tz_kr)
                    tw_dt = kr_dt.astimezone(tz_tw)
                    time_formatted = tw_dt.strftime("%m/%d %H:%M")
                except Exception:
                    time_formatted = f"{now_tw.strftime('%m/%d')} 17:30"
                
                away = KBO_MAP.get(away_raw, away_raw)
                home = KBO_MAP.get(home_raw, home_raw)
                lines.append(f"{time_formatted} ⏰ {away} vs {home}")
                count += 1
                
            if count == 0:
                lines.append("24 小時內無賽事")
    except Exception as e:
        lines.append(f"⚠️ 數據連線異常: {e}")

    lines.append("\n──────────────\n")
    lines.append("‼️ 通知:定時 記得下注")

    return "\n".join(lines)

def send_telegram_msg(text: str):
    """發送訊息至 Telegram 群組"""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_GROUP_ID:
        return {"error": "未設定 TELEGRAM_BOT_TOKEN 或 TELEGRAM_GROUP_ID"}
        
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_GROUP_ID,
        "text": text,
        "parse_mode": "Markdown"
    }
    res = requests.post(url, json=payload, timeout=10)
    return res.json()

# 端點 1: 純文字輸出 (ManyChat / 網頁瀏覽)
@app.get("/")
@app.get("/schedule")
def get_schedule_text():
    text = build_schedule_text()
    return Response(content=text, media_type="text/plain; charset=utf-8")

# 端點 2: JSON 格式輸出
@app.get("/api/schedule")
def get_schedule_json():
    text = build_schedule_text()
    return {"status": "success", "data": text}

# 端點 3: Cron-Job 雲端觸發 Telegram 自動推播專用
@app.get("/push_telegram")
def trigger_push():
    content = build_schedule_text()
    result = send_telegram_msg(content)
    return {"status": "success", "telegram_response": result}

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port)
