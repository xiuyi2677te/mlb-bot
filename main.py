import os
import datetime
import pytz
import requests
import logging
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

# 設定標準 Log 輸出
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

STATUS_MAP = {
    "Scheduled": "預定", "Pre-Game": "賽前", "In Progress": "進行中", 
    "Final": "完賽", "Game Over": "完賽", "Postponed": "延賽", "Cancelled": "取消"
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

def fetch_sports_data(url, name):
    """通用 API 請求與嚴格診斷包裝器"""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    try:
        res = requests.get(url, headers=headers, timeout=8)
        if res.status_code == 200:
            return True, res.json(), None
        else:
            reason = f"伺服器拒絕連線 (HTTP {res.status_code})"
            logging.error(f"[{name}] {reason}")
            return False, None, reason
    except requests.exceptions.Timeout:
        reason = "網路連線逾時 (Timeout)"
        logging.error(f"[{name}] {reason}")
        return False, None, reason
    except Exception as e:
        reason = f"連線異常 ({type(e).__name__})"
        logging.error(f"[{name}] {reason}")
        return False, None, reason

def get_mlb_games():
    """MLB 美職 (官方 API 驗證)"""
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
        success, data, err_msg = fetch_sports_data(url, "MLB API")
        
        if success and data and 'dates' in data:
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

    valid_games.sort(key=lambda x: x['datetime'])

    if valid_games:
        return "⚾ **🇺🇸 MLB 美職 未來 24 小時賽事**\n\n" + "\n".join([g['text'] for g in valid_games])
    else:
        return "⚾ **🇺🇸 MLB 美職 未來 24 小時賽事**\n未來 24 小時內無賽事安排或休兵日。"

def get_npb_games():
    """NPB 日棒 (帶真實錯誤回報機制)"""
    url = "https://site.api.espn.com/apis/site/v2/sports/baseball/japan.1/scoreboard"
    success, data, err_msg = fetch_sports_data(url, "NPB API")
    
    if not success:
        return f"⚾ **🇯🇵 NPB 日棒 未來 24 小時賽事**\n❌ 抓取失敗 (原因: {err_msg})"
        
    valid_games = []
    events = data.get('events', []) if data else []
    
    for ev in events:
        name = ev.get('name', '')
        status_str = ev.get('status', {}).get('type', {}).get('shortDetail', '')
        if name:
            valid_games.append(f"⏰ {name} ({status_str})")

    if valid_games:
        return "⚾ **🇯🇵 NPB 日棒 未來 24 小時賽事**\n\n" + "\n".join(valid_games)
    else:
        return "⚾ **🇯🇵 NPB 日棒 未來 24 小時賽事**\n未來 24 小時內無賽事安排或休兵日。"

def get_kbo_games():
    """KBO 韓職 (帶真實錯誤回報機制)"""
    url = "https://site.api.espn.com/apis/site/v2/sports/baseball/kor.1/scoreboard"
    success, data, err_msg = fetch_sports_data(url, "KBO API")
    
    if not success:
        return f"⚾ **🇰🇷 KBO 韓職 未來 24 小時賽事**\n❌ 抓取失敗 (原因: {err_msg})"
        
    valid_games = []
    events = data.get('events', []) if data else []
    
    for ev in events:
        name = ev.get('name', '')
        status_str = ev.get('status', {}).get('type', {}).get('shortDetail', '')
        if name:
            valid_games.append(f"⏰ {name} ({status_str})")

    if valid_games:
        return "⚾ **🇰🇷 KBO 韓職 未來 24 小時賽事**\n\n" + "\n".join(valid_games)
    else:
        return "⚾ **🇰🇷 KBO 韓職 未來 24 小時賽事**\n未來 24 小時內無賽事安排或休兵日。"

def build_full_report():
    mlb_msg = get_mlb_games()
    npb_msg = get_npb_games()
    kbo_msg = get_kbo_games()
    return f"☀️️ **未來 24 小時棒球賽事彙整**\n\n{mlb_msg}\n\n--------------------\n\n{npb_msg}\n\n--------------------\n\n{kbo_msg}"

async def schedule_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    report = build_full_report()
    try:
        await update.message.reply_text(report, parse_mode="Markdown")
    except Exception as e:
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
                logging.error(f"Push to {cid} failed: {e}")

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

    logging.info("🤖 棒球賽事 Telegram Bot 已啟動...")
    app.run_polling()

if __name__ == "__main__":
    main()
