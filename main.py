import os
import datetime
import pytz
import requests
import logging
import threading
from bs4 import BeautifulSoup
from http.server import HTTPServer, BaseHTTPRequestHandler
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

# 隊伍名稱對照表 (英文/原名 -> 繁體中文)
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
    "阪神": "阪神虎", "巨人": "讀賣巨人", "DeNA": "橫濱 BayStars",
    "中日": "中日龍", "広島": "廣島鯉魚", "ヤクルト": "養樂多燕子",
    "ソフトバンク": "軟銀鷹", "ロッテ": "羅德海洋", "オリックス": "歐力士野牛",
    "楽天": "東北樂天金鷲", "西武": "西武獅", "日本ハム": "日本火腿鬥士"
}

KBO_TEAM_MAP = {
    "LG": "LG 雙子", "KT": "KT 巫師", "SSG": "SSG 蘭德斯", "NC": "NC 恐龍",
    "두산": "斗山熊", "KIA": "起亞虎", "롯데": "樂天巨人", "삼성": "三星獅",
    "한화": "韓華鷹", "키움": "培證英雄"
}

class SimpleHTTPRequestHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Baseball Bot Pro Scraper is running!")

def run_web_server():
    port = int(os.environ.get("PORT", 10000))
    server = HTTPServer(('0.0.0.0', port), SimpleHTTPRequestHandler)
    server.serve_forever()

# --- 1. MLB 官方 API 引擎 (時區修正版) ---
def get_mlb_games(now_tw, tz_tw):
    # 查詢範圍：台灣時間昨天 ~ 台灣時間明天 (完整覆蓋美東時差)
    start_str = (now_tw - datetime.timedelta(days=1)).strftime("%Y-%m-%d")
    end_str = (now_tw + datetime.timedelta(days=1)).strftime("%Y-%m-%d")
    
    url = f"https://statsapi.mlb.com/api/v1/schedule?sportId=1&startDate={start_str}&endDate={end_str}"
    games_list = []
    
    try:
        res = requests.get(url, timeout=10)
        res.raise_for_status()
        data = res.json()
        
        for d in data.get('dates', []):
            for g in d.get('games', []):
                utc_str = g.get('gameDate')
                if not utc_str:
                    continue
                
                utc_dt = datetime.datetime.fromisoformat(utc_str.replace('Z', '+00:00'))
                tw_dt = utc_dt.astimezone(tz_tw)

                # 嚴格過濾：未來 24 小時內
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
        
        games_list.sort(key=lambda x: x['dt'])
        return games_list, None
    except Exception as e:
        logging.error(f"MLB 抓取失敗: {e}")
        return [], str(e)

# --- 2. NPB 日棒爬蟲 (Yahoo Japan 頻道) ---
def get_npb_games(now_tw, tz_tw):
    tz_jp = pytz.timezone('Asia/Tokyo')
    now_jp = now_tw.astimezone(tz_jp)
    
    # 抓取今天與明天 (日本時間)
    dates_jp = [
        now_jp.strftime("%Y%m%d"),
        (now_jp + datetime.timedelta(days=1)).strftime("%Y%m%d")
    ]
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept-Language": "ja-JP,ja;q=0.9"
    }
    
    games_list = []
    seen_matches = set()
    
    try:
        for d_str in dates_jp:
            url = f"https://baseball.yahoo.co.jp/npb/schedule/?date={d_str}"
            res = requests.get(url, headers=headers, timeout=10)
            if res.status_code != 200:
                continue
                
            soup = BeautifulSoup(res.text, 'html.parser')
            items = soup.select('.bb-score__item')
            
            for item in items:
                teams = item.select('.bb-score__team')
                if len(teams) < 2:
                    continue
                
                away_raw = teams[0].get_text(strip=True)
                home_raw = teams[1].get_text(strip=True)
                
                info_elem = item.select_one('.bb-score__link') or item.select_one('.bb-score__info')
                info_text = info_elem.get_text(strip=True) if info_elem else ""
                
                # 嘗試提取開打時間 (例如 18:00)
                time_part = ""
                for word in info_text.split():
                    if ":" in word and len(word) <= 5:
                        time_part = word
                        break
                
                if not time_part:
                    time_part = "18:00" # 預設榜定賽事時間
                
                # 轉換日本時間為台灣時間
                try:
                    game_jp_dt = tz_jp.localize(datetime.datetime.strptime(f"{d_str} {time_part}", "%Y%m%d %H:%M"))
                    game_tw_dt = game_jp_dt.astimezone(tz_tw)
                except Exception:
                    continue
                
                if not (now_tw <= game_tw_dt <= (now_tw + datetime.timedelta(hours=24))):
                    continue
                
                match_key = f"{game_tw_dt.strftime('%m%d%H%M')}_{away_raw}_{home_raw}"
                if match_key in seen_matches:
                    continue
                seen_matches.add(match_key)
                
                status_zh = "完賽" if "終了" in info_text else ("進行中" if "回" in info_text else "預定")
                
                def translate_npb(raw):
                    for k, v in NPB_TEAM_MAP.items():
                        if k in raw:
                            return v
                    return raw
                
                home_zh = translate_npb(home_raw)
                away_zh = translate_npb(away_raw)
                
                games_list.append({
                    'dt': game_tw_dt,
                    'text': f"⏰ **{game_tw_dt.strftime('%m/%d %H:%M')}** | {away_zh} vs {home_zh} ({status_zh})"
                })
        
        games_list.sort(key=lambda x: x['dt'])
        return games_list, None
    except Exception as e:
        logging.error(f"NPB 爬蟲失敗: {e}")
        return [], str(e)

# --- 3. KBO 韓職數據引擎 (Naver Sports API) ---
def get_kbo_games(now_tw, tz_tw):
    tz_kr = pytz.timezone('Asia/Seoul')
    now_kr = now_tw.astimezone(tz_kr)
    
    dates_kr = [
        now_kr.strftime("%Y-%m-%d"),
        (now_kr + datetime.timedelta(days=1)).strftime("%Y-%m-%d")
    ]
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }
    
    games_list = []
    seen_game_ids = set()
    
    try:
        for d_str in dates_kr:
            url = f"https://sports.news.naver.com/schedule/scoreboards?date={d_str}&category=kbo"
            res = requests.get(url, headers=headers, timeout=10)
            if res.status_code != 200:
                continue
                
            data = res.json()
            # Naver Scoreboard JSON 結構
            scoreboard_list = data.get('data', {}).get('scoreboardList', []) or data.get('scoreboardList', [])
            
            for g in scoreboard_list:
                game_id = g.get('gameId') or g.get('gId')
                if game_id and game_id in seen_game_ids:
                    continue
                if game_id:
                    seen_game_ids.add(game_id)
                
                time_str_raw = g.get('gameStartTime', '18:30')
                try:
                    game_kr_dt = tz_kr.localize(datetime.datetime.strptime(f"{d_str} {time_str_raw}", "%Y-%m-%d %H:%M"))
                    game_tw_dt = game_kr_dt.astimezone(tz_tw)
                except Exception:
                    continue
                
                if not (now_tw <= game_tw_dt <= (now_tw + datetime.timedelta(hours=24))):
                    continue
                
                status_code = g.get('statusCode', '')
                status_zh = "完賽" if status_code in ["RESULT", "END"] else ("進行中" if status_code == "IN" else "預定")
                if g.get('cancel', False):
                    status_zh = "延賽/取消"
                
                away_raw = g.get('awayTeamName', '')
                home_raw = g.get('homeTeamName', '')
                
                def translate_kbo(raw):
                    for k, v in KBO_TEAM_MAP.items():
                        if k in raw:
                            return v
                    return raw
                
                home_zh = translate_kbo(home_raw)
                away_zh = translate_kbo(away_raw)
                
                games_list.append({
                    'dt': game_tw_dt,
                    'text': f"⏰ **{game_tw_dt.strftime('%m/%d %H:%M')}** | {away_zh} vs {home_zh} ({status_zh})"
                })
                
        games_list.sort(key=lambda x: x['dt'])
        return games_list, None
    except Exception as e:
        logging.error(f"KBO 數據抓取失敗: {e}")
        return [], str(e)

# --- 整合輸出 ---
def get_baseball_schedule():
    tz_tw = pytz.timezone('Asia/Taipei')
    now_tw = datetime.datetime.now(tz_tw)

    mlb_games, mlb_err = get_mlb_games(now_tw, tz_tw)
    npb_games, npb_err = get_npb_games(now_tw, tz_tw)
    kbo_games, kbo_err = get_kbo_games(now_tw, tz_tw)

    def format_section(title, games, err):
        if err:
            return f"⚾ **{title}**\n⚠️ 數據連線異常: {err}"
        if games:
            return f"⚾ **{title}**\n\n" + "\n".join([g['text'] for g in games])
        return f"⚾ **{title}**\n未來 24 小時內無賽事安排或休兵日。"

    mlb_text = format_section("🇺🇸 MLB 美職 未來 24 小時賽事", mlb_games, mlb_err)
    npb_text = format_section("🇯🇵 NPB 日棒 未來 24 小時賽事", npb_games, npb_err)
    kbo_text = format_section("🇰🇷 KBO 韓職 未來 24 小時賽事", kbo_games, kbo_err)

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

    logging.info("🤖 棒球賽事 Telegram Bot (生產級爬蟲引擎版) 已啟動...")
    app.run_polling()

if __name__ == "__main__":
    main()
