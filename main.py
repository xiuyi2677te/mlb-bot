import os
import datetime
import pytz
import requests
import logging
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

# 隊伍名稱對照表 (英文 -> 繁體中文)
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
    "Tigers": "阪神虎", "Giants": "讀賣巨人", "BayStars": "橫濱 BayStars",
    "Dragons": "中日龍", "Carp": "廣島鯉魚", "Swallows": "養樂多燕子",
    "Hawks": "軟銀鷹", "Marines": "羅德海洋", "Buffaloes": "歐力士野牛",
    "Eagles": "東北樂天金鷲", "Lions": "西武獅", "Fighters": "日本火腿鬥士"
}

KBO_TEAM_MAP = {
    "Twins": "LG 雙子", "Wiz": "KT 巫師", "Landers": "SSG 蘭德斯", "Dinos": "NC 恐龍",
    "Bears": "斗山熊", "Tigers": "起亞虎", "Giants": "樂天巨人", "Lions": "三星獅",
    "Eagles": "韓華鷹", "Heroes": "培證英雄"
}

class SimpleHTTPRequestHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Baseball Bot is running via Direct Public APIs!")

def run_web_server():
    port = int(os.environ.get("PORT", 10000))
    server = HTTPServer(('0.0.0.0', port), SimpleHTTPRequestHandler)
    server.serve_forever()

# --- 1. MLB 官方 API (statsapi.mlb.com) ---
def get_mlb_games(now_tw, tz_tw):
    today_str = now_tw.strftime("%Y-%m-%d")
    tomorrow_str = (now_tw + datetime.timedelta(days=1)).strftime("%Y-%m-%d")
    url = f"https://statsapi.mlb.com/api/v1/schedule?sportId=1&startDate={today_str}&endDate={tomorrow_str}"
    
    games_list = []
    try:
        res = requests.get(url, timeout=10).json()
        dates = res.get('dates', [])
        for d in dates:
            for g in d.get('games', []):
                game_utc_str = g.get('gameDate') # ISO UTC
                utc_dt = datetime.datetime.fromisoformat(game_utc_str.replace('Z', '+00:00'))
                tw_dt = utc_dt.astimezone(tz_tw)

                # 篩選未來 24 小時內
                if not (now_tw <= tw_dt <= (now_tw + datetime.timedelta(hours=24))):
                    continue

                status_raw = g.get('status', {}).get('detailedState', '預定')
                status_zh = "完賽" if "Final" in status_raw else ("進行中" if "In Progress" in status_raw else "預定")

                teams = g.get('teams', {})
                home_raw = teams.get('home', {}).get('team', {}).get('name', '')
                away_raw = teams.get('away', {}).get('team', {}).get('name', '')

                home_zh = MLB_TEAM_MAP.get(home_raw, home_raw)
                away_zh = MLB_TEAM_MAP.get(away_raw, away_raw)

                time_str = tw_dt.strftime("%H:%M")
                date_str = tw_dt.strftime("%m/%d")

                games_list.append({
                    'dt': tw_dt,
                    'text': f"⏰ **{date_str} {time_str}** | {away_zh} vs {home_zh} ({status_zh})"
                })
    except Exception as e:
        logging.error(f"MLB 官方 API 抓取失敗: {e}")
    
    games_list.sort(key=lambda x: x['dt'])
    return games_list

# --- 2. 日棒/韓職 ESPN 免費 API ---
def get_espn_games(league_code, team_map, now_tw, tz_tw):
    dates = [now_tw.strftime("%Y%m%d"), (now_tw + datetime.timedelta(days=1)).strftime("%Y%m%d")]
    games_list = []
    seen_ids = set()

    for d in dates:
        url = f"https://site.api.espn.com/apis/site/v2/sports/baseball/{league_code}/scoreboard?dates={d}"
        try:
            res = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=10).json()
            events = res.get('events', [])
            for event in events:
                event_id = event.get('id')
                if not event_id or event_id in seen_ids:
                    continue

                game_utc_str = event.get('date')
                utc_dt = datetime.datetime.fromisoformat(game_utc_str.replace('Z', '+00:00'))
                tw_dt = utc_dt.astimezone(tz_tw)

                if not (now_tw <= tw_dt <= (now_tw + datetime.timedelta(hours=24))):
                    continue

                seen_ids.add(event_id)

                status_type = event.get('status', {}).get('type', {}).get('name', '')
                status_zh = "完賽" if "FINAL" in status_type else ("進行中" if "IN_PROGRESS" in status_type else "預定")

                competitors = event.get('competitions', [{}])[0].get('competitors', [])
                home_raw, away_raw = "", ""
                for c in competitors:
                    name = c.get('team', {}).get('name', '')
                    if c.get('homeAway') == 'home':
                        home_raw = name
                    else:
                        away_raw = name

                def translate(name):
                    for k, v in team_map.items():
                        if k.lower() in name.lower():
                            return v
                    return name

                home_zh = translate(home_raw)
                away_zh = translate(away_raw)

                time_str = tw_dt.strftime("%H:%M")
                date_str = tw_dt.strftime("%m/%d")

                games_list.append({
                    'dt': tw_dt,
                    'text': f"⏰ **{date_str} {time_str}** | {away_zh} vs {home_zh} ({status_zh})"
                })
        except Exception as e:
            logging.error(f"ESPN API ({league_code}) 抓取失敗: {e}")

    games_list.sort(key=lambda x: x['dt'])
    return games_list

def get_baseball_schedule():
    tz_tw = pytz.timezone('Asia/Taipei')
    now_tw = datetime.datetime.now(tz_tw)

    mlb_games = get_mlb_games(now_tw, tz_tw)
    npb_games = get_espn_games('japan.1', NPB_TEAM_MAP, now_tw, tz_tw)
    kbo_games = get_espn_games('kor.1', KBO_TEAM_MAP, now_tw, tz_tw)

    def format_section(title, games):
        if games:
            return f"⚾ **{title}**\n\n" + "\n".join([g['text'] for g in games])
        else:
            return f"⚾ **{title}**\n未來 24 小時內無賽事安排或休兵日。"

    mlb_text = format_section("🇺🇸 MLB 美職 未來 24 小時賽事", mlb_games)
    npb_text = format_section("🇯🇵 NPB 日棒 未來 24 小時賽事", npb_games)
    kbo_text = format_section("🇰🇷 KBO 韓職 未來 24 小時賽事", kbo_games)

    return f"☀️ **未來 24 小時棒球賽事彙整**\n\n{mlb_text}\n\n--------------------\n\n{npb_text}\n\n--------------------\n\n{kbo_text}"

async def schedule_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    report = get_baseball_schedule()
    try:
        await update.message.reply_text(report, parse_mode="Markdown")
    except Exception:
        if update.effective_chat:
            await context.bot.send_message(chat_id=update.effective_chat.id, text=report, parse_mode="Markdown")

async def scheduled_push(context: ContextTypes.DEFAULT_TYPE):
    if CHAT_ID:
        report = get_baseball_schedule()
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

    logging.info("🤖 棒球賽事 Telegram Bot (直連免 API Key 版) 已啟動...")
    app.run_polling()

if __name__ == "__main__":
    main()
