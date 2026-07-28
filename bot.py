import os
import time
import threading
import logging
import traceback

import telebot
from telebot import apihelper
from flask import Flask

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger("price-bot")

# ---------- فحص الإعدادات الأساسية عند البدء ----------
BOT_TOKEN = os.environ.get("BOT_TOKEN")
if not BOT_TOKEN:
    raise RuntimeError("لازم تحدد متغير البيئة BOT_TOKEN بإعدادات Render")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FONT_PATH = os.path.join(BASE_DIR, "Cairo.ttf")
if not os.path.exists(FONT_PATH):
    # نسجل خطأ واضح بدل ما نخلي البرنامج ينهار بصمت وقت لأول صورة توصل
    log.error(f"⚠️ ملف الخط غير موجود بالمسار: {FONT_PATH}")
    log.error("تأكد إن Cairo.ttf مرفوع بنفس مجلد المشروع بـ GitHub.")

# نستورد بعد التأكد، وأي فشل هنا يطلع بالـ log بوضوح
try:
    from price_stamp import draw_price_box
    PRICE_STAMP_OK = True
except Exception:
    log.error("فشل استيراد price_stamp.py:\n" + traceback.format_exc())
    PRICE_STAMP_OK = False

apihelper.RETRY_ON_ERROR = True  # يعيد المحاولة تلقائياً على أخطاء الشبكة المؤقتة
bot = telebot.TeleBot(BOT_TOKEN, parse_mode=None, threaded=True)

# ---------- خادم صغير بس لأجل UptimeRobot يخلي الخدمة صاحية ----------
app = Flask(__name__)
bot_status = {"running": False, "last_error": None, "restarts": 0}


@app.route("/")
def health():
    state = "alive ✅" if bot_status["running"] else "starting/restarting ⚠️"
    return (
        f"price bot status: {state} | restarts: {bot_status['restarts']} "
        f"| last_error: {bot_status['last_error']}"
    ), 200


# ---------- منطق البوت ----------
WELCOME = (
    "أهلاً! 👋\n"
    "أرسل صورة المنتج مع كتابة السعر بنفس الرسالة (caption).\n"
    "مثال:\n"
    "12 زوج\n"
    "67 الف\n\n"
    "وراح أرجعلك نفس الصورة وفيها صندوق السعر جاهز."
)


@bot.message_handler(commands=["start", "help"])
def handle_start(message):
    try:
        bot.reply_to(message, WELCOME)
    except Exception:
        log.error("فشل إرسال رسالة الترحيب:\n" + traceback.format_exc())


@bot.message_handler(content_types=["photo"])
def handle_photo(message):
    if not PRICE_STAMP_OK:
        bot.reply_to(
            message,
            "⚠️ البوت لسه ما جاهز تماماً (مشكلة إعداد داخلية). خبر المسؤول التقني.",
        )
        return

    caption = (message.caption or "").strip()
    if not caption:
        bot.reply_to(
            message,
            "⚠️ ما لكيت نص السعر. لازم تكتب السعر بنفس رسالة الصورة (caption)، مو برسالة منفصلة.",
        )
        return

    input_path = None
    output_path = None
    try:
        file_id = message.photo[-1].file_id
        file_info = bot.get_file(file_id)
        downloaded = bot.download_file(file_info.file_path)

        input_path = f"/tmp/{file_id}_in.jpg"
        output_path = f"/tmp/{file_id}_out.jpg"
        with open(input_path, "wb") as f:
            f.write(downloaded)

        draw_price_box(input_path, caption, output_path)

        with open(output_path, "rb") as f:
            bot.send_photo(message.chat.id, f)

    except Exception:
        error_text = traceback.format_exc()
        log.error(f"فشل معالجة صورة من {message.chat.id}:\n{error_text}")
        try:
            bot.reply_to(
                message,
                "⚠️ صار خطأ بمعالجة هذي الصورة تحديداً. جرب صورة ثانية، "
                "وإذا تكررت المشكلة خبرني بالتفصيل.",
            )
        except Exception:
            log.error("فشل حتى إرسال رسالة الخطأ للمستخدم:\n" + traceback.format_exc())

    finally:
        # تنظيف الملفات المؤقتة دائماً حتى لو صار خطأ
        for p in (input_path, output_path):
            if p and os.path.exists(p):
                try:
                    os.remove(p)
                except Exception:
                    pass


@bot.message_handler(func=lambda m: True, content_types=["text"])
def handle_text(message):
    try:
        bot.reply_to(message, "أرسل الصورة مع كتابة السعر بنفس الرسالة (caption)، مو نص لحاله.")
    except Exception:
        log.error("فشل الرد على رسالة نصية:\n" + traceback.format_exc())


# ---------- حلقة تشغيل صلبة: تعيد البوت تلقائياً لو انهار ----------
def run_bot_forever():
    while True:
        try:
            bot_status["running"] = True
            log.info("بدء/إعادة تشغيل بوت تيليجرام (polling)...")
            try:
                bot.remove_webhook()
            except Exception:
                pass
            bot.infinity_polling(skip_pending=True, timeout=30, long_polling_timeout=30)
        except Exception:
            error_text = traceback.format_exc()
            log.error("انهار البوت بخطأ غير متوقع، راح يعيد المحاولة خلال 5 ثواني:\n" + error_text)
            bot_status["running"] = False
            bot_status["last_error"] = str(error_text.strip().splitlines()[-1]) if error_text else "unknown"
            bot_status["restarts"] += 1
            time.sleep(5)
        else:
            # infinity_polling ما يفترض يخلص عادي، بس لو خلص نعيده احتياط
            bot_status["running"] = False
            log.warning("توقف polling بدون خطأ واضح، إعادة التشغيل خلال 5 ثواني...")
            time.sleep(5)


if __name__ == "__main__":
    threading.Thread(target=run_bot_forever, daemon=True).start()
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
