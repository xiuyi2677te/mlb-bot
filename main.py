import os
import datetime
import pytz
import requests
import logging
import json
import re
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from bs4 import BeautifulSoup

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

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

NPB_TEAM_MAP = {
    "阪神": "阪神虎", "巨人": "讀賣巨人", "DeNA": "橫濱 BayStars", "中日": "中日龍",
    "広島": "廣島鯉魚", "ヤクルト": "養樂多燕子", "ソフトバンク": "軟銀鷹", "ロッテ": "羅德海洋",
    "オリックス": "歐力士野牛", "楽天": "東北樂天金鷲", "西武": "西武獅", "日本ハム": "日本火腿鬥士"
}

KBO_TEAM_MAP = {
    "LG": "LG 雙子", "KT": "KT 巫師", "SSG": "SSG 蘭德斯", "NC": "NC 恐龍",
    "두산": "斗山熊", "KIA": "起亞虎", "롯데": "樂天巨人", "삼성": "三星獅",
    "한화": "韓華鷹", "키움": "培證英雄"
}

STATUS_MAP = {
    "Scheduled": "預定", "Pre-Game": "賽前", "In Progress": "進行中", 
    "Final": "完賽", "Game Over": "完賽", "Postponed": "延賽", "Cancelled": "取消",
    "BEFORE": "預定", "LIVE": "進行中", "RESULT": "完賽", "READY": "預定"
}

class SimpleHTTPRequestHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Baseball Bot is running on Render!")

def run_web_server():
    port = int(os.environ.get("PORT", 10000))
    server = HTTPServer(('0.0.0.0', port), SimpleHTTPRequestHandler)
    server.serve_forever()

# ----------------- 1. MLB 官方 API -----------------
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
            res = requests.get(url, timeout=8)
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
        except Exception as e:
            logging.error(f"MLB 抓取異常: {e}")

    valid_games.sort(key=lambda x: x['datetime'])

    if valid_games:
        return "⚾ **🇺🇸 MLB 美職 未來 24 小時賽事**\n\n" + "\n".join([g['text'] for g in valid_games])
    else:
        return "⚾ **🇺🇸 MLB 美職 未來 24 小時賽事**\n未來 24 小時內無賽事安排或休兵日。"

# ----------------- 2. NPB 精準解析器 (完全切斷側邊欄與歷史賽事干擾) -----------------
def get_npb_games():
    tz_tw = pytz.timezone('Asia/Taipei')
    now_tw = datetime.datetime.now(tz_tw)
    date_str = now_tw.strftime("%Y-%m-%d")
    
    url = f"https://baseball.yahoo.co.jp/npb/schedule/?date={date_str}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36",
        "Referer": "https://baseball.yahoo.co.jp/npb/"
    }
    
    try:
        res = requests.get(url, headers=headers, timeout=8)
        if res.status_code != 200:
            return f"⚾ **🇯🇵 NPB 日棒 未來 24 小時賽事**\n❌ 抓取失敗 (HTTP 狀態碼: {res.status_code})"
        
        soup = BeautifulSoup(res.text, 'html.parser')
        
        # 關鍵修復：強制限縮在 #main 核心內容區，排除 #sub 側邊欄與歷史戰績列表
        main_content = soup.find('div', id='main') or soup.find('main') or soup
        score_items = main_content.find_all('section', class_='bb-score__item')
        
        valid_games = []
        for item in score_items:
            teams = item.find_all('p', class_='bb-score__team')
            time_tag = item.find('p', class_='bb-score__link') or item.find('span', class_='bb-score__time')
            
            if len(teams) >= 2:
                away_raw = teams[0].get_text(strip=True)
                home_raw = teams[1].get_text(strip=True)
                status_raw = time_tag.get_text(strip=True) if time_tag else "預定"
                
                away_zh = next((v for k, v in NPB_TEAM_MAP.items() if k in away_raw), None)
                home_zh = next((v for k, v in NPB_TEAM_MAP.items() if k in home_raw), None)
                
                if away_zh and home_zh:
                    valid_games.append(f"⏰ **{now_tw.strftime('%m/%d')}** | {away_zh} vs {home_zh} ({status_raw})")

        valid_games = list(dict.fromkeys(valid_games))

        if valid_games:
            return "⚾ **🇯🇵 NPB 日棒 未來 24 小時賽事**\n\n" + "\n".join(valid_games)
        else:
            return "⚾ **🇯🇵 NPB 日棒 未來 24 小時賽事**\n未來 24 小時內無賽事安排或休兵日。"
            
    except Exception as e:
        return f"⚾ **🇯🇵 NPB 日棒 未來 24 小時賽事**\n❌ 抓取失敗 (原因: {type(e).__name__})"

# ----------------- 3. KBO (防護突破標頭與動態請求) -----------------
def get_kbo_games():
    tz_tw = pytz.timezone('Asia/Taipei')
    now_tw = datetime.datetime.now(tz_tw)
    date_str_daum = now_tw.strftime("%Y%m%d")
    date_str_naver = now_tw.strftime("%Y-%m-%d")
    
    full_browser_headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "zh-TW,zh;q=0.9,en-US;q=0.8,en;q=0.7,ko;q=0.6",
        "Sec-Ch-Ua": '"Google Chrome";v="129", "Not=A?Brand";v="8", "Chromium";v="129"',
        "Sec-Ch-Ua-Mobile": "?0",
        "Sec-Ch-Ua-Platform": '"Windows"',
        "Sec-Fetch-Dest": "empty",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "same-site"
    }
    
    # 優先嘗試 Source 1: Daum API
    daum_url = f"https://sports.daum.net/prx/api/mda/schedule/kbo?date={date_str_daum}"
    try:
        headers_daum = full_browser_headers.copy()
        headers_daum["Referer"] = "https://sports.daum.net/schedule/kbo"
        res_daum = requests.get(daum_url, headers=headers_daum, timeout=6)
        
        if res_daum.status_code == 200 and "html" not in res_daum.headers.get("Content-Type", "").lower() and not res_daum.text.strip().startswith("<"):
            data = res_daum.json()
            schedules = data.get('schedule', []) or data.get('data', [])
            valid_games = []
            
            for item in schedules:
                away_raw = item.get('awayTeamName', '')
                home_raw = item.get('homeTeamName', '')
                status_raw = item.get('status', 'BEFORE')
                time_raw = item.get('startTime', '17:30')
                
                away_zh = next((v for k, v in KBO_TEAM_MAP.items() if k in away_raw), away_raw)
                home_zh = next((v for k, v in KBO_TEAM_MAP.items() if k in home_raw), home_raw)
                status_zh = STATUS_MAP.get(status_raw, status_raw)
                
                if away_zh and home_zh:
                    valid_games.append(f"⏰ **{now_tw.strftime('%m/%d')} {time_raw[:5]}** | {away_zh} vs {home_zh} ({status_zh})")
            
            if valid_games:
                return "⚾ **🇰🇷 KBO 韓職 未來 24 小時賽事**\n\n" + "\n".join(valid_games)
    except Exception as e:
        logging.warning(f"Daum API 抓取失敗: {e}")

    # 備援 Source 2: Naver API
    naver_url = f"https://m.sports.naver.com/api/game/kbaseball/schedule?date={date_str_naver}"
    try:
        headers_naver = full_browser_headers.copy()
        headers_naver["Referer"] = "https://m.sports.naver.com/kbaseball/schedule/index"
        res_naver = requests.get(naver_url, headers=headers_naver, timeout=6)
        
        if res_naver.status_code == 200 and not res_naver.text.strip().startswith("<"):
            data = res_naver.json()
            games_list = data.get('gamelist', []) or data.get('mappedSchedule', [])
            valid_games = []
            
            for g in games_list:
                away_raw = g.get('awayTeamName', '')
                home_raw = g.get('homeTeamName', '')
                time_raw = g.get('gameStartTime', '17:30')
                status_raw = g.get('gameStatusCode', 'BEFORE')
                
                away_zh = next((v for k, v in KBO_TEAM_MAP.items() if k in away_raw), away_raw)
                home_zh = next((v for k, v in KBO_TEAM_MAP.items() if k in home_raw), home_raw)
                status_zh = STATUS_MAP.get(status_raw, status_raw)
                
                if away_zh and home_zh:
                    valid_games.append(f"⏰ **{now_tw.strftime('%m/%d')} {time_raw[:5]}** | {away_zh} vs {home_zh} ({status_zh})")
            
            if valid_games:
                return "⚾ **🇰🇷 KBO 韓職 未來 24 小時賽事**\n\n" + "\n".join(valid_games)
    except Exception as e:
        logging.error(f"Naver 備援 API 亦失敗: {e}")

    return "⚾ **🇰🇷 KBO 韓職 未來 24 小時賽事**\n未來 24 小時內無賽事安排或韓國伺服器維護中。"

# ----------------- 4. 訊息彙整與 Telegram Bot 核心 -----------------
def build_full_report():
    mlb_msg = get_mlb_games()
    npb_msg = get_npb_games()
    kbo_msg = get_kbo_games()
    return f"☀️ **未來 24 小時棒球賽事彙整**\n\n{mlb_msg}\n\n--------------------\n\n{npb_msg}\n\n--------------------\n\n{kbo_msg}"

async def schedule_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    report = build_full_report()
    try:
        await update.message.reply_text(report, parse_mode="Markdown")
    except Exception:
        if update.effective_chat:
            await context.bot.send_message(chat_id=update.effective_chat.id, text=report, parse_mode="Markdown")

async def scheduled_push(context: ContextTypes.DEFAULT_TYPE):
    if CHAT_ID:
        report = build_full_report()
        chat_ids = [c.strip() for c in CHAT_ID.split(",") if c.strip()]
        for cid in chat_ids:
            try:
                await context.bot.send_message(chat_id=cid, text=report, parse_mode="Markdown")
            except Exception as e:
                logging.error(f"推播至 {cid} 失敗: {e}")

def main():
    if not TELEGRAM_BOT_TOKEN:
        logging.critical("❌ 未設定 TELEGRAM_BOT_TOKEN")
        return

    threading.Thread(target=run_web_server, daemon=True).start()

    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    app.add_handler(CommandHandler("schedule", schedule_command))

    tz_tw = pytz.timezone('Asia/Taipei')
    push_times = [
        datetime.time(hour=11, minute=0, tzinfo=tz_tw),
        datetime.time(hour=15, minute=0, tzinfo=tz_tw),
        datetime.time(hour=19, minute=0, tzinfo=tz_tw),
        datetime.time(hour=22, minute=0, tzinfo=tz_tw)
    ]
    
    for t in push_times:
        app.job_queue.run_daily(scheduled_push, time=t)

    logging.info("🤖 棒球賽事 Telegram Bot 已成功啟動...")
    app.run_polling()

if __name__ == "__main__":
    main()
