import os
import datetime
import pytz
import urllib.request
import json
import re
import ssl
import logging
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from telegram import Update, BotCommand
from telegram.ext import Application, CommandHandler, ContextTypes

# 設定標準 Log 輸出
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID", "-5208269046,-5502209076,-5344474800")

# SSL 與時區設定
ssl_ctx = ssl._create_unverified_context()
tz_tw = datetime.timezone(datetime.timedelta(hours=8))
tz_kr = datetime.timezone(datetime.timedelta(hours=9))

# 防重複推播記憶體快取: "game_id_reminder_type"
notified_games = set()

# MLB 全 30 隊中文名稱對照表
MLB_MAP = {
    "Tampa Bay Rays": "光芒", "New York Yankees": "洋基", "Boston Red Sox": "紅襪",
    "Baltimore Orioles": "金鶯", "Toronto Blue Jays": "藍鳥", "Los Angeles Dodgers": "道奇",
    "San Francisco Giants": "巨人", "San Diego Padres": "教士", "Arizona Diamondbacks": "響尾蛇",
    "Colorado Rockies": "落磯", "Atlanta Braves": "勇士", "Philadelphia Phillies": "費城人",
    "New York Mets": "大都會", "Miami Marlins": "馬林魚", "Washington Nationals": "國民",
    "Chicago Cubs": "小熊", "Milwaukee Brewers": "釀酒人", "St. Louis Cardinals": "紅雀",
    "Cincinnati Reds": "紅人", "Pittsburgh Pirates": "海盜", "Houston Astros": "太空人",
    "Texas Rangers": "遊騎兵", "Seattle Mariners": "水手", "Oakland Athletics": "運動家",
    "Los Angeles Angels": "天使", "Cleveland Guardians": "守護者", "Minnesota Twins": "雙城",
    "Detroit Tigers": "老虎", "Kansas City Royals": "皇家", "Chicago White Sox": "白襪"
}

# NPB 隊伍中文名稱對照表
NPB_MAP = {
    "阪神": "阪神虎", "広島": "廣島鯉魚", "巨人": "讀賣巨人", 
    "DeNA": "橫濱", "ＤｅＮＡ": "橫濱", "横浜": "橫濱",
    "中日": "中日龍", "ヤクルト": "養樂多", "ソフトバンク": "軟銀鷹",
    "ロッテ": "羅德海洋", "オリックス": "歐力士", "楽天": "樂天金鷲",
    "西武": "西武獅", "日本ハム": "日本火腿", "日ハム": "日本火腿"
}

# KBO 隊伍中文名稱對照表
KBO_MAP = {
    "LG": "LG雙子", "두산": "斗山熊", "SSG": "SSG蘭德斯", "NC": "NC恐龍",
    "키움": "培證英雄", "한화": "韓華鷹", "롯데": "樂天巨人", "KIA": "起亞虎",
    "KT": "KT巫師", "삼성": "三星獅"
}

# NBA 全 30 隊中文名稱對照表
NBA_MAP = {
    "Hawks": "老鷹", "Atlanta Hawks": "老鷹", "Atlanta": "老鷹",
    "Celtics": "塞爾提克", "Boston Celtics": "塞爾提克", "Boston": "塞爾提克",
    "Nets": "籃網", "Brooklyn Nets": "籃網", "Brooklyn": "籃網",
    "Hornets": "黃蜂", "Charlotte Hornets": "黃蜂", "Charlotte": "黃蜂",
    "Bulls": "公牛", "Chicago Bulls": "公牛", "Chicago": "公牛",
    "Cavaliers": "騎士", "Cleveland Cavaliers": "騎士", "Cleveland": "騎士",
    "Mavericks": "獨行俠", "Dallas Mavericks": "獨行俠", "Dallas": "獨行俠",
    "Nuggets": "金塊", "Denver Nuggets": "金塊", "Denver": "金塊",
    "Pistons": "活塞", "Detroit Pistons": "活塞", "Detroit": "活塞",
    "Warriors": "勇士", "Golden State Warriors": "勇士", "Golden State": "勇士",
    "Rockets": "火箭", "Houston Rockets": "火箭", "Houston": "火箭",
    "Pacers": "溜馬", "Indiana Pacers": "溜馬", "Indiana": "溜馬",
    "Clippers": "快艇", "LA Clippers": "快艇", "Los Angeles Clippers": "快艇",
    "Lakers": "湖人", "Los Angeles Lakers": "湖人", "LA Lakers": "湖人",
    "Grizzlies": "灰熊", "Memphis Grizzlies": "灰熊", "Memphis": "灰熊",
    "Heat": "熱火", "Miami Heat": "熱火", "Miami": "熱火",
    "Bucks": "公鹿", "Milwaukee Bucks": "公鹿", "Milwaukee": "公鹿",
    "Timberwolves": "灰狼", "Minnesota Timberwolves": "灰狼", "Minnesota": "灰狼",
    "Pelicans": "鵜鶘", "New Orleans Pelicans": "鵜鶘", "New Orleans": "鵜鶘",
    "Knicks": "尼克", "New York Knicks": "尼克", "New York": "尼克",
    "Thunder": "雷霆", "Oklahoma City Thunder": "雷霆", "Oklahoma City": "雷霆",
    "Magic": "魔術", "Orlando Magic": "魔術", "Orlando": "魔術",
    "76ers": "76人", "Philadelphia 76ers": "76人", "Philadelphia": "76人",
    "Suns": "太陽", "Phoenix Suns": "太陽", "Phoenix": "太陽",
    "Trail Blazers": "拓荒者", "Portland Trail Blazers": "拓荒者", "Portland": "拓荒者",
    "Kings": "國王", "Sacramento Kings": "國王", "Sacramento": "國王",
    "Spurs": "馬刺", "San Antonio Spurs": "馬刺", "San Antonio": "馬刺",
    "Raptors": "暴龍", "Toronto Raptors": "暴龍", "Toronto": "暴龍",
    "Jazz": "爵士", "Utah Jazz": "爵士", "Utah": "爵士",
    "Wizards": "巫師", "Washington Wizards": "巫師", "Washington": "巫師"
}

# ----------------------------------------------------
# Render 伺服器防休眠連接埠設定 (含 GET 與 HEAD)
# ----------------------------------------------------
class SimpleHTTPRequestHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-type', 'text/html')
        self.end_headers()
        self.wfile.write(b"Sports Bot is running on Render!")

    def do_HEAD(self):
        self.send_response(200)
        self.send_header('Content-type', 'text/html')
        self.end_headers()

def run_web_server():
    port = int(os.environ.get("PORT", 10000))
    server = HTTPServer(('0.0.0.0', port), SimpleHTTPRequestHandler)
    server.serve_forever()

# ----------------------------------------------------
# 取得未來 24 小時結構化賽事資料列表
# ----------------------------------------------------
def get_upcoming_games_list() -> list:
    now_tw = datetime.datetime.now(tz_tw)
    future_24h = now_tw + datetime.timedelta(hours=24)
    games_list = []

    # [1] MLB 美職
    try:
        start_d = (now_tw - datetime.timedelta(days=1)).strftime("%Y-%m-%d")
        end_d = (now_tw + datetime.timedelta(days=1)).strftime("%Y-%m-%d")
        url_mlb = f"https://statsapi.mlb.com/api/v1/schedule?sportId=1&startDate={start_d}&endDate={end_d}"
        req = urllib.request.Request(url_mlb, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, context=ssl_ctx, timeout=10) as resp:
            data = json.loads(resp.read().decode('utf-8'))
            for date_item in data.get('dates', []):
                for game in date_item.get('games', []):
                    utc_str = game.get('gameDate')
                    if not utc_str: continue
                    utc_dt = datetime.datetime.fromisoformat(utc_str.replace('Z', '+00:00'))
                    game_dt = utc_dt.astimezone(tz_tw)
                    if now_tw <= game_dt <= future_24h:
                        game_pk = str(game.get('gamePk', ''))
                        away_raw = game.get('teams', {}).get('away', {}).get('team', {}).get('name', '未知')
                        home_raw = game.get('teams', {}).get('home', {}).get('team', {}).get('name', '未知')
                        away = MLB_MAP.get(away_raw, away_raw)
                        home = MLB_MAP.get(home_raw, home_raw)
                        games_list.append({
                            'id': f"MLB_{game_pk}_{game_dt.timestamp()}",
                            'league': '⚾ 🇺🇸 MLB 美職',
                            'time': game_dt,
                            'away': away,
                            'home': home
                        })
    except Exception as e:
        logging.error(f"MLB fetch error: {e}")

    # [2] NPB 日棒
    dates_to_check = [
        now_tw.strftime("%Y-%m-%d"),
        (now_tw + datetime.timedelta(days=1)).strftime("%Y-%m-%d")
    ]
    headers_npb = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
        'Accept-Language': 'ja,en-US;q=0.9,en;q=0.8'
    }
    seen_npb = set()
    for date_str in dates_to_check:
        url_npb = f"https://baseball.yahoo.co.jp/npb/schedule/?date={date_str}"
        try:
            req = urllib.request.Request(url_npb, headers=headers_npb)
            with urllib.request.urlopen(req, context=ssl_ctx, timeout=10) as resp:
                html = resp.read().decode('utf-8')
                cards = re.findall(r'class="bb-score__item"[\s\S]*?</section>', html) or \
                        re.findall(r'<div class="bb-score__content">[\s\S]*?</div>\s*</div>', html) or \
                        re.findall(r'<tr class="bb-calendarTable__row">[\s\S]*?</tr>', html)
                
                for card in cards:
                    found_teams = []
                    for team_key, team_cn in NPB_MAP.items():
                        if team_key in card and team_cn not in found_teams:
                            found_teams.append(team_cn)
                    
                    if len(found_teams) == 2:
                        time_match = re.search(r'(\d{1,2}:\d{2})', card)
                        jst_time = time_match.group(1) if time_match else "18:00"
                        hh = int(jst_time.split(':')[0]) - 1
                        mm = jst_time.split(':')[1]
                        g_dt = datetime.datetime.strptime(f"{date_str} {hh:02d}:{mm}", "%Y-%m-%d %H:%M").replace(tzinfo=tz_tw)
                        
                        if now_tw <= g_dt <= future_24h:
                            key = f"{found_teams[0]}_{found_teams[1]}_{g_dt.timestamp()}"
                            if key not in seen_npb:
                                seen_npb.add(key)
                                games_list.append({
                                    'id': f"NPB_{key}",
                                    'league': '⚾ 🇯🇵 NPB 日棒',
                                    'time': g_dt,
                                    'away': found_teams[0],
                                    'home': found_teams[1]
                                })
        except Exception as e:
            logging.error(f"NPB fetch error: {e}")

    # [3] KBO 韓職
    try:
        today_kr = now_tw.strftime("%Y-%m-%d")
        tomorrow_kr = (now_tw + datetime.timedelta(days=1)).strftime("%Y-%m-%d")
        url_kbo = f"https://api-gw.sports.naver.com/schedule/games?upperCategoryId=kbaseball&fromDate={today_kr}&toDate={tomorrow_kr}"
        headers_kbo = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Referer': 'https://sports.news.naver.com/',
            'Accept': 'application/json, text/plain, */*'
        }
        req = urllib.request.Request(url_kbo, headers=headers_kbo)
        with urllib.request.urlopen(req, context=ssl_ctx, timeout=10) as resp:
            data = json.loads(resp.read().decode('utf-8'))
            result = data.get('result', {})
            games = result.get('games', []) or data.get('games', []) or []
            for g in games:
                away_raw = g.get('awayTeamName')
                home_raw = g.get('homeTeamName')
                if not away_raw or not home_raw: continue
                g_date_str = g.get('gameDate') or today_kr
                kst_time_str = g.get('gameStartTime') or g.get('startTime') or "18:30"
                try:
                    kr_dt = datetime.datetime.strptime(f"{g_date_str} {kst_time_str}", "%Y-%m-%d %H:%M").replace(tzinfo=tz_kr)
                    game_dt = kr_dt.astimezone(tz_tw)
                except Exception:
                    continue
                if now_tw <= game_dt <= future_24h:
                    away = KBO_MAP.get(away_raw, away_raw)
                    home = KBO_MAP.get(home_raw, home_raw)
                    games_list.append({
                        'id': f"KBO_{away}_{home}_{game_dt.timestamp()}",
                        'league': '⚾ 🇰🇷 KBO 韓職',
                        'time': game_dt,
                        'away': away,
                        'home': home
                    })
    except Exception as e:
        logging.error(f"KBO fetch error: {e}")

    # [4] NBA 籃球 (改用 ESPN 萬無一失的即時 Schedule API)
    try:
        # 同時抓取今天與明天的 ESPN NBA API
        dates_nba = [
            now_tw.strftime("%Y%m%d"),
            (now_tw + datetime.timedelta(days=1)).strftime("%Y%m%d")
        ]
        seen_nba_ids = set()
        
        for d_str in dates_nba:
            url_nba = f"https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard?dates={d_str}"
            req = urllib.request.Request(url_nba, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, context=ssl_ctx, timeout=10) as resp:
                data = json.loads(resp.read().decode('utf-8'))
                for event in data.get('events', []):
                    game_id = str(event.get('id', ''))
                    if game_id in seen_nba_ids: continue
                    
                    utc_str = event.get('date')
                    if not utc_str: continue
                    utc_dt = datetime.datetime.fromisoformat(utc_str.replace('Z', '+00:00'))
                    game_dt = utc_dt.astimezone(tz_tw)

                    if now_tw <= game_dt <= future_24h:
                        seen_nba_ids.add(game_id)
                        competitions = event.get('competitions', [{}])[0]
                        competitors = competitions.get('competitors', [])
                        
                        away_raw, home_raw = "未知", "未知"
                        for comp in competitors:
                            t_name = comp.get('team', {}).get('displayName', '')
                            s_name = comp.get('team', {}).get('name', '')
                            cn_mapped = NBA_MAP.get(t_name) or NBA_MAP.get(s_name) or s_name or t_name
                            
                            if comp.get('homeAway') == 'away':
                                away_raw = cn_mapped
                            else:
                                home_raw = cn_mapped

                        games_list.append({
                            'id': f"NBA_{game_id}",
                            'league': '🏀 🇺🇸 NBA 籃球',
                            'time': game_dt,
                            'away': away_raw,
                            'home': home_raw
                        })
    except Exception as e:
        logging.error(f"NBA fetch error: {e}")

    return games_list

# ----------------------------------------------------
# 賽事戰報文字組裝邏輯
# ----------------------------------------------------
def build_full_report() -> str:
    games = get_upcoming_games_list()
    lines = ["☀️ 未來 24 小時體育賽事彙整\n"]

    leagues = [
        '⚾ 🇺🇸 MLB 美職',
        '⚾ 🇯🇵 NPB 日棒',
        '⚾ 🇰🇷 KBO 韓職',
        '🏀 🇺🇸 NBA 籃球'
    ]

    for lg in leagues:
        lines.append(lg)
        lg_games = [g for g in games if g['league'] == lg]
        if lg_games:
            for g in lg_games:
                lines.append(f"{g['time'].strftime('%m/%d %H:%M')} ⏰ {g['away']} vs {g['home']}")
        else:
            lines.append("24 小時內無賽事")
        lines.append("\n──────────────\n")

    lines.append("‼️ 通知:定時 記得下注")
    return "\n".join(lines)

# ----------------------------------------------------
# 即時開打提醒邏輯 (賽前 10 分鐘與 5 分鐘)
# ----------------------------------------------------
async def check_and_send_game_reminders(context: ContextTypes.DEFAULT_TYPE):
    now_tw = datetime.datetime.now(tz_tw)
    games = get_upcoming_games_list()

    reminder_rules = [
        {'type': '10min', 'label': '10 分鐘', 'min_sec': 540, 'max_sec': 660},
        {'type': '5min',  'label': '5 分鐘',  'min_sec': 240, 'max_sec': 360}
    ]

    for rule in reminder_rules:
        target_games = []
        for g in games:
            diff_sec = (g['time'] - now_tw).total_seconds()
            key = f"{g['id']}_{rule['type']}"

            if rule['min_sec'] <= diff_sec <= rule['max_sec'] and key not in notified_games:
                target_games.append((g, key))

        if target_games:
            lines = [f"🚨 賽事開打預告 (剩餘 {rule['label']})\n"]
            grouped_by_league = {}
            for g, key in target_games:
                grouped_by_league.setdefault(g['league'], []).append(g)
                notified_games.add(key)

            for league_name, lg_games in grouped_by_league.items():
                lines.append(league_name)
                for g in lg_games:
                    lines.append(f"{g['time'].strftime('%m/%d %H:%M')} ⏰ {g['away']} vs {g['home']}")
                lines.append("")

            lines.append("──────────────")
            lines.append("‼️ 提醒：比賽即將開始，請確認下注狀況！")

            msg = "\n".join(lines)
            chat_ids = [c.strip() for c in CHAT_ID.split(",") if c.strip()]
            for cid in chat_ids:
                try:
                    await context.bot.send_message(chat_id=cid, text=msg)
                except Exception as e:
                    logging.error(f"Reminder push to {cid} failed: {e}")

# ----------------------------------------------------
# Telegram Bot 指令處理
# ----------------------------------------------------
async def schedule_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """處理群組中的 /schedule 指令"""
    report = build_full_report()
    try:
        await update.message.reply_text(report)
    except Exception as e:
        if update.effective_chat:
            await context.bot.send_message(chat_id=update.effective_chat.id, text=report)

async def test_reminder_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """處理群組中的 /test_reminder 指令"""
    games = get_upcoming_games_list()
    if not games:
        await update.message.reply_text("⚠️ 目前未來 24 小時內沒有抓到任何賽事可供測試。")
        return

    sample_game = games[0]
    lines = [
        "🧪 【模擬測試】賽事開打預告 (剩餘 10 分鐘)\n",
        sample_game['league'],
        f"{sample_game['time'].strftime('%m/%d %H:%M')} ⏰ {sample_game['away']} vs {sample_game['home']}\n",
        "──────────────",
        "‼️ 提醒：比賽即將開始，請確認下注狀況！"
    ]
    await update.message.reply_text("\n".join(lines))

async def post_init(application: Application):
    """Bot 啟動時自動註冊 Telegram 指令選單"""
    commands = [
        BotCommand("schedule", "📊 獲取未來24小時賽事戰報"),
        BotCommand("test_reminder", "🧪 測試賽事推播")
    ]
    await application.bot.set_my_commands(commands)

async def scheduled_push(context: ContextTypes.DEFAULT_TYPE):
    """定時自動推播"""
    if CHAT_ID:
        report = build_full_report()
        chat_ids = [c.strip() for c in CHAT_ID.split(",") if c.strip()]
        for cid in chat_ids:
            try:
                await context.bot.send_message(chat_id=cid, text=report)
            except Exception as e:
                logging.error(f"Push to {cid} failed: {e}")

def main():
    if not TELEGRAM_BOT_TOKEN:
        logging.critical("❌ 未設定 TELEGRAM_BOT_TOKEN")
        return

    threading.Thread(target=run_web_server, daemon=True).start()

    app = Application.builder().token(TELEGRAM_BOT_TOKEN).post_init(post_init).build()
    
    app.add_handler(CommandHandler("schedule", schedule_command))
    app.add_handler(CommandHandler("test_reminder", test_reminder_command))

    tz_taipei = pytz.timezone('Asia/Taipei')
    push_times = [
        datetime.time(hour=11, minute=0, tzinfo=tz_taipei),
        datetime.time(hour=15, minute=0, tzinfo=tz_taipei),
        datetime.time(hour=23, minute=0, tzinfo=tz_taipei)
    ]
    for t in push_times:
        app.job_queue.run_daily(scheduled_push, time=t)

    app.job_queue.run_repeating(check_and_send_game_reminders, interval=60, first=10)

    logging.info("🤖 體育賽事 Telegram Bot 已啟動（包含 MLB/NPB/KBO/NBA）...")
    app.run_polling()

if __name__ == "__main__":
    main()
