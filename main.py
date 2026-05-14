from flask import Flask, request
import telebot
from telebot import types
import os

TOKEN = os.environ.get("BOT_TOKEN")
bot = telebot.TeleBot(TOKEN)

app = Flask(__name__)

# ==================== КЛАВИАТУРЫ ====================
def main_keyboard():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    markup.row("🏋️ Тренировка")
    markup.row("📏 Замеры", "📅 История")
    markup.row("🏋️‍♀️ Прогресс", "📚 Библиотека")
    markup.row("😩 Сегодня нет сил")
    return markup

def workout_inline():
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(types.InlineKeyboardButton("Д1 — Ноги/ягодицы", callback_data="day_Д1"))
    markup.add(types.InlineKeyboardButton("Д2 — Спина/плечи", callback_data="day_Д2"))
    return markup

# ==================== ОБРАБОТЧИКИ ====================
@bot.message_handler(commands=['start'])
def start(message):
    bot.send_message(
        message.chat.id,
        f"Привет, {message.from_user.first_name}! 👋\n\nТвой фитнес-бот готов.",
        reply_markup=main_keyboard()
    )

@bot.message_handler(func=lambda m: True)
def handle_message(message):
    text = (message.text or "").strip()
    
    if "Тренировка" in text or "🏋️" in text:
        bot.send_message(message.chat.id, "Выбери день тренировки:", reply_markup=workout_inline())
    else:
        bot.send_message(message.chat.id, "Используй кнопки меню 👇", reply_markup=main_keyboard())

@bot.callback_query_handler(func=lambda call: True)
def callback_query(call):
    if call.data.startswith("day_"):
        day = call.data.replace("day_", "")
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.id,
            text=f"🏋️ Тренировка — {day}\n\nПрограмма дня будет здесь.",
            reply_markup=None
        )

# ==================== WEBHOOK ====================
@app.route('/' + TOKEN, methods=['POST'])
def webhook():
    json_str = request.get_data().decode('UTF-8')
    update = telebot.types.Update.de_json(json_str)
    bot.process_new_updates([update])
    return 'OK', 200

@app.route('/')
def index():
    return "Фитнес-бот работает на Render ✅"

# ==================== ЗАПУСК ====================
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
