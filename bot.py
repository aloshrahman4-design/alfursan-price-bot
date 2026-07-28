import os
import io
import threading
import logging

import telebot
from flask import Flask

from price_stamp import draw_price_box

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("price-bot")

BOT_TOKEN = os.environ.get("BOT_TOKEN")
if not BOT_TOKEN:
    raise RuntimeError("لازم تحدد متغير البيئة BOT_TOKEN")

bot = telebot.TeleBot(BOT_TOKEN, parse_mode=None)

# ---------- خادم صغير بس لأجل UptimeRobot يخلي الخدمة صاحية ----------
app = Flask(__name__)


@app.route("/")
def health():
    return "OK - price bot is alive", 200


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
    bot.reply_to(message, WELCOME)


@bot.message_handler(content_types=["photo"])
def handle_photo(message):
    caption = (message.caption or "").strip()

    if not caption:
        bot.reply_to(
            message,
            "⚠️ ما لكيت نص السعر. لازم تكتب السعر بنفس رسالة الصورة (caption)، مو برسالة منفصلة.",
        )
        return

    try:
        # نأخذ أعلى جودة متوفرة من الصورة
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

        os.remove(input_path)
        os.remove(output_path)

    except Exception as e:
        log.exception("فشل بمعالجة الصورة")
        bot.reply_to(message, f"⚠️ صار خطأ بمعالجة الصورة: {e}")


@bot.message_handler(func=lambda m: True, content_types=["text"])
def handle_text(message):
    bot.reply_to(message, "أرسل الصورة مع كتابة السعر بنفس الرسالة (caption)، مو نص لحاله.")


def run_bot():
    log.info("بدء تشغيل بوت تيليجرام (polling)...")
    bot.infinity_polling(skip_pending=True)


if __name__ == "__main__":
    threading.Thread(target=run_bot, daemon=True).start()
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
