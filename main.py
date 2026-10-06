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

# ----------------- 2. NPB 萬用結構相容解析器 -----------------
def get_npb_games():
    tz_tw = pytz.timezone('Asia/Taipei')
    now_tw = datetime.datetime.now(tz_tw)
    date_str = now_tw.strftime("%Y-%m-%d")
    
    url = f"https://baseball.yahoo.co.jp/npb/schedule/?date={date_str}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36"
    }
    
    try:
        res = requests.get(url, headers=headers, timeout=8)
        if res.status_code != 200:
            return f"⚾ **🇯🇵 NPB 日棒 未來 24 小時賽事**\n❌ 請求失敗 (HTTP {res.status_code})"
        
        soup = BeautifulSoup(res.text, 'html.parser')
        main_content = soup.find('div', id='main') or soup.find('main') or soup
        
        valid_games = []
        
        # 掃描核心區塊內的最小單元節點
        sub_elements = main_content.find_all(['section', 'div', 'li', 'tr'])
        for el in sub_elements:
            text = el.get_text(" ", strip=True)
            matched_teams = []
            
            for jp_key, zh_name in NPB_TEAM_MAP.items():
                if jp_key in text and zh_name not in matched_teams:
                    matched_teams.append(zh_name)
            
            # 若單一區塊剛好匹配 2 支日棒隊伍
            if len(matched_teams) == 2:
                time_match = re.search(r'\b(1[0-9]|2[0-3]|[0-9]):[0-5][0-9]\b', text)
                time_str = f" {time_match.group(0)}" if time_match else ""
                
                game_str = f"⏰ **{now_tw.strftime('%m/%d')}{time_str}** | {matched_teams[0]} vs {matched_teams[1]}"
                if game_str not in valid_games:
                    valid_games.append(game_str)

        # 保底容錯：若標籤層級過深，使用內文正規化比對
        if not valid_games:
            raw_matches = re.findall(r'(阪神|巨人|DeNA|中日|広島|ヤクルト|ソフトバンク|ロッテ|オリックス|楽天|西武|日本ハム)\s*vs?\s*(阪神|巨人|DeNA|中日|広島|ヤクルト|ソフトバンク|ロッテ|オリックス|楽天|西武|日本ハム)', res.text)
            for m in raw_matches:
                t1 = NPB_TEAM_MAP.get(m[0], m[0])
                t2 = NPB_TEAM_MAP.get(m[1], m[1])
                if t1 != t2:
                    valid_games.append(f"⏰ **{now_tw.strftime('%m/%d')}** | {t1} vs {t2}")

        valid_games = list(dict.fromkeys(valid_games))

        if valid_games:
            return "⚾ **🇯🇵 NPB 日棒 未來 24 小時賽事**\n\n" + "\n".join(valid_games)
        else:
            return "⚾ **🇯🇵 NPB 日棒 未來 24 小時賽事**\n未來 24 小時內無賽事安排或休兵日。"
            
    except Exception as e:
        return f"⚾ **🇯🇵 NPB 日棒 未來 24 小時賽事**\n❌ 抓取失敗 ({type(e).__name__})"

# ----------------- 3. KBO 官方 API 直連 (突破機房 IP 封鎖) -----------------
def get_kbo_games():
    tz_tw = pytz.timezone('Asia/Taipei')
    now_tw = datetime.datetime.now(tz_tw)
    date_str_kbo = now_tw.strftime("%Y%m%d")
    
    valid_games = []
    
    # 策略 1: 直連 KBO 官方網站 AJAX 介面 (不鎖機房 IP)
    try:
        kbo_url = "https://www.koreabaseball.com/ws/Main.bs"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Referer": "https://www.koreabaseball.com/"
        }
        res = requests.post(kbo_url, headers=headers, timeout=6)
        if res.status_code == 200:
            try:
                data = res.json()
                schedules = data.get('ltMainSchedule', []) or data.get('ltSchedule', [])
                for item in schedules:
                    away_raw = item.get('AWAY_NM', '') or item.get('awayName', '')
                    home_raw = item.get('HOME_NM', '') or item.get('homeName', '')
                    time_raw = item.get('G_TIME', '17:30')
                    status_raw = item.get('GAME_STATE_SC', 'BEFORE')
                    
                    away_zh = next((v for k, v in KBO_TEAM_MAP.items() if k in away_raw), away_raw)
                    home_zh = next((v for k, v in KBO_TEAM_MAP.items() if k in home_raw), home_raw)
                    status_zh = STATUS_MAP.get(status_raw, status_raw)
                    
                    if away_zh and home_zh:
                        valid_games.append(f"⏰ **{now_tw.strftime('%m/%d')} {time_raw[:5]}** | {away_zh} vs {home_zh} ({status_zh})")
            except Exception:
                pass
    except Exception as e:
        logging.warning(f"KBO 官方 API 請求異常: {e}")

    # 策略 2: Daum API 備援
    if not valid_games:
        try:
            daum_url = f"https://sports.daum.net/prx/api/mda/schedule/kbo?date={date_str_kbo}"
            headers_daum = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Referer": "https://sports.daum.net/schedule/kbo"
            }
            res_daum = requests.get(daum_url, headers=headers_daum, timeout=6)
            if res_daum.status_code == 200 and not res_daum.text.strip().startswith("<"):
                data = res_daum.json()
                schedules = data.get('schedule', []) or data.get('data', [])
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
        except Exception:
            pass

    valid_games = list(dict.fromkeys(valid_games))

    if valid_games:
        return "⚾ **🇰🇷 KBO 韓職 未來 24 小時賽事**\n\n" + "\n".join(valid_games)
    else:
        return "⚾ **🇰🇷 KBO 韓職 未來 24 小時賽事**\n未來 24 小時內無賽事安排或休兵日。"

# ----------------- 4. Telegram 機器人核心 -----------------
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
