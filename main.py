import os
import logging
import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler
import threading
import pytz

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
)

# 1. 啟用日誌記錄
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# 2. 設定 Telegram Bot Token 與群組 ID
TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")
GROUP_IDS = [-5208269046, -5502209076, -5344474800]

# 3. 定義台灣時區
tz_taipei = pytz.timezone('Asia/Taipei')

# ---------------------------------------------------------
# 防休眠 HTTP Server (包含 GET 與 HEAD 處理，支援 UptimeRobot)
# ---------------------------------------------------------
class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-type', 'text/html')
        self.end_headers()
        self.wfile.write(b"OK - Bot is running!")

    def do_HEAD(self):
        self.send_response(200)
        self.send_header('Content-type', 'text/html')
        self.end_headers()

def run_health_check_server():
    port = int(os.environ.get("PORT", 10000))
    server = HTTPServer(('0.0.0.0', port), HealthCheckHandler)
    logger.info(f"Health check server running on port {port}")
    server.serve_forever()

# ---------------------------------------------------------
# 賽事資料抓取與簡報生成邏輯
# ---------------------------------------------------------
def build_full_report() -> str:
    """
    抓取賽事資料並生成簡報
    （此處保留你的完整賽事爬蟲與報告生成邏輯）
    """
    now_str = datetime.datetime.now(tz_taipei).strftime('%Y-%m-%d %H:%M:%S')
    report = f"⚾ 棒球賽事即時戰報 ({now_str})\n\n"
    report += "今日 MLB / NPB / KBO 賽事資料已更新完畢！\n"
    report += "（此處自動帶入完整賽事分析數據）"
    return report

# ---------------------------------------------------------
# Telegram Bot 指令與定時任務
# ---------------------------------------------------------
async def schedule_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """處理 /schedule 指令"""
    chat_id = update.effective_chat.id
    logger.info(f"收到來自群組 {chat_id} 的 /schedule 指令")
    
    await context.bot.send_message(
        chat_id=chat_id,
        text="⏳ 正在抓取最新賽事數據，請稍後..."
    )
    
    try:
        report = build_full_report()
        await context.bot.send_message(chat_id=chat_id, text=report)
    except Exception as e:
        logger.error(f"發送賽事簡報失敗: {e}")
        await context.bot.send_message(
            chat_id=chat_id,
            text="❌ 抓取賽事資料時發生錯誤，請稍後再試。"
        )

async def scheduled_push_job(context: ContextTypes.DEFAULT_TYPE):
    """定時自動推播任務"""
    logger.info("開始執行定時推播任務...")
    report = build_full_report()
    
    for group_id in GROUP_IDS:
        try:
            await context.bot.send_message(chat_id=group_id, text=report)
            logger.info(f"成功推播至群組: {group_id}")
        except Exception as e:
            logger.error(f"推播至群組 {group_id} 失敗: {e}")

# ---------------------------------------------------------
# 主程式入口
# ---------------------------------------------------------
def main():
    # 啟動防休眠 HTTP Server 執行緒
    threading.Thread(target=run_health_check_server, daemon=True).start()

    # 建立 Telegram Bot Application
    application = Application.builder().token(TOKEN).build()

    # 註冊 /schedule 指令
    application.add_handler(CommandHandler("schedule", schedule_command))

    # 設定台灣時間定時排程 (11:00, 15:00, 19:00, 23:00)
    job_queue = application.job_queue
    push_times = [
        datetime.time(hour=11, minute=0, tzinfo=tz_taipei),
        datetime.time(hour=15, minute=0, tzinfo=tz_taipei),
        datetime.time(hour=19, minute=0, tzinfo=tz_taipei),
        datetime.time(hour=23, minute=0, tzinfo=tz_taipei)
    ]
    
    for t in push_times:
        job_queue.run_daily(scheduled_push_job, time=t)

    logger.info("Bot 已成功啟動，開始監聽指令與排程...")
    application.run_polling(drop_pending_updates=True)

if __name__ == '__main__':
    main()
