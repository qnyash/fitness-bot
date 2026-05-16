import os
import json
import random
import io
import telebot
from telebot import types
from flask import Flask, request
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime
import matplotlib.pyplot as plt

TOKEN = os.environ.get("BOT_TOKEN")
bot = telebot.TeleBot(TOKEN)
app = Flask(__name__)

ADMIN_ID = 466924747
CHANNEL_ID = -1003457894028

# ================= ПОДКЛЮЧЕНИЕ К GOOGLE SHEETS =================
gc = None
sh = None
try:
    creds_json = os.environ.get('GOOGLE_CREDENTIALS')
    creds_dict = json.loads(creds_json)
    scopes = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
    credentials = Credentials.from_service_account_info(creds_dict, scopes=scopes)
    gc = gspread.authorize(credentials)
    sh = gc.open_by_url(os.environ.get('SPREADSHEET_URL'))
except Exception as e:
    pass

def init_db():
    if not sh: return
    worksheets = [ws.title for ws in sh.worksheets()]
    if 'Users' not in worksheets:
        ws = sh.add_worksheet(title="Users", rows=100, cols=5); ws.append_row(['user_id', 'name', 'date_joined'])
    if 'Program' not in worksheets:
        ws = sh.add_worksheet(title="Program", rows=100, cols=5); ws.append_row(['day', 'exercise', 'sets', 'reps'])
    if 'History' not in worksheets:
        ws = sh.add_worksheet(title="History", rows=100, cols=5); ws.append_row(['date', 'user_id', 'name', 'day', 'status'])
    if 'Progress' not in worksheets:
        ws = sh.add_worksheet(title="Progress", rows=100, cols=3); ws.append_row(['date', 'user_id', 'note'])
    if 'Library' not in worksheets:
        ws = sh.add_worksheet(title="Library", rows=100, cols=4); ws.append_row(['category', 'name', 'description', 'image_url'])
    if 'Motivation' not in worksheets:
        ws = sh.add_worksheet(title="Motivation", rows=100, cols=1); ws.append_row(['text'])
    if 'Measurements' not in worksheets:
        ws = sh.add_worksheet(title="Measurements", rows=100, cols=9); ws.append_row(['date', 'user_id', 'weight', 'height', 'shoulders', 'chest', 'waist', 'butt', 'hips'])
    if 'KBZHU' not in worksheets:
        ws = sh.add_worksheet(title="KBZHU", rows=100, cols=7); ws.append_row(['date', 'user_id', 'weight', 'height', 'age', 'activity', 'calories'])

init_db()

active_workouts = {}
user_states = {}
meas_temp = {} 
kbzhu_temp = {} 

def get_program_from_sheet(day):
    if not sh: return []
    try:
        ws = sh.worksheet("Program")
        return [r for r in ws.get_all_records() if str(r.get('day', '')) == day]
    except: return []

def get_lib_categories():
    if not sh: return []
    try:
        ws = sh.worksheet("Library")
        cats = [str(r.get('category', '')) for r in ws.get_all_records() if r.get('category')]
        return list(set(cats))
    except: return []

def get_lib_exercises(cat):
    if not sh: return []
    try:
        ws = sh.worksheet("Library")
        return [r for r in ws.get_all_records() if str(r.get('category', '')) == cat]
    except: return []

# ================= ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ДЛЯ ТРЕНИРОВОК =================
def get_workout_text(user_id):
    workout = active_workouts.get(user_id)
    if not workout: return ""
    text = f"🏋️ **Тренировка: {workout['day']}**\n\n"
    completed_sets = workout.get('completed_sets', {})
    for i, ex in enumerate(workout['program']):
        sets_count = int(ex.get('sets', 1))
        done_count = len(completed_sets.get(i, []))
        # Зеленая галочка, если все подходы сделаны
        status = "✅" if done_count == sets_count else "⬜" 
        text += f"{status} **{ex.get('exercise', 'Упр')}** ({done_count}/{sets_count})\n"
    return text

def workout_keyboard(user_id):
    markup = types.InlineKeyboardMarkup()
    workout = active_workouts.get(user_id)
    if not workout: return markup

    program = workout['program']
    completed_sets = workout.get('completed_sets', {})

    for i, ex in enumerate(program):
        sets_count = int(ex.get('sets', 1))
        reps = ex.get('reps', '0')
        row = []
        for s in range(sets_count):
            is_done = s in completed_sets.get(i, [])
            # Салют вместо галочки для подходов
            label = "🫡" if is_done else f"{s+1}️⃣" 
            row.append(types.InlineKeyboardButton(f"{label} {sets_count}x{reps}", callback_data=f"set_{i}_{s}"))
        markup.row(*row) # Добавляем подходы в одну строку

    markup.add(types.InlineKeyboardButton("🏁 Завершить тренировку", callback_data="finish"))
    return markup

# ================= КЛАВИАТУРЫ МЕНЮ =================
def main_keyboard(user_id):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    markup.row("🏋️ Тренировка", "📏 Замеры")
    markup.row("📈 Прогресс", "🥗 КБЖУ")
    markup.row("📚 Библиотека", "😩 Сегодня нет сил")
    markup.row("📅 История")
    if user_id == ADMIN_ID:
        markup.row("⚙️ Админ-панель")
    return markup

# ================= ХЭНДЛЕРЫ СООБЩЕНИЙ =================

@bot.message_handler(commands=['start'])
def start(message):
    user_id = message.from_user.id
    user_states[user_id] = None
    if sh:
        try:
            ws = sh.worksheet("Users")
            if str(user_id) not in ws.col_values(1):
                ws.append_row([str(user_id), message.from_user.first_name, datetime.now().strftime("%Y-%m-%d %H:%M")])
        except: pass
    welcome_text = f"Привет, {message.from_user.first_name}! 🍑\nГотова растрясти булочки?"
    bot.send_message(message.chat.id, welcome_text, reply_markup=main_keyboard(user_id))

@bot.message_handler(func=lambda m: m.from_user.id in kbzhu_temp and 'weight' not in kbzhu_temp.get(m.from_user.id, {}))
def kbzhu_input_handler(message):
    user_id = message.from_user.id
    text = message.text.strip()
    u = kbzhu_temp[user_id]
    if 'age' not in u:
        try: u['age'] = int(text); bot.send_message(user_id, "Введи свой рост (см):")
        except: bot.send_message(user_id, "Пожалуйста, введи число.")
    elif 'height' not in u:
        try: u['height'] = int(text); bot.send_message(user_id, "Введи свой вес (кг):")
        except: bot.send_message(user_id, "Пожалуйста, введи число.")
    elif 'weight' not in u:
        try:
            u['weight'] = int(text)
            markup = types.InlineKeyboardMarkup(row_width=1)
            markup.add(types.InlineKeyboardButton("🛋 Сидячий", callback_data="kbzhu_act_1.2_Сидячий"))
            markup.add(types.InlineKeyboardButton("🚶 Легкая (1-3 р/н)", callback_data="kbzhu_act_1.375_Легкая"))
            markup.add(types.InlineKeyboardButton("🏋️ Средняя (3-5 р/н)", callback_data="kbzhu_act_1.55_Средняя"))
            markup.add(types.InlineKeyboardButton("🔥 Высокая (каждый день)", callback_data="kbzhu_act_1.725_Высокая"))
            bot.send_message(user_id, "Выбери уровень активности:", reply_markup=markup)
        except: bot.send_message(user_id, "Пожалуйста, введи число.")

@bot.message_handler(func=lambda m: m.from_user.id in meas_temp)
def meas_input_handler(message):
    user_id = message.from_user.id
    text = message.text.strip()
    step = meas_temp.get('step', '')
    if step == 'weight': meas_temp['weight'] = text; meas_temp['step'] = 'height'; bot.send_message(user_id, "Введи Рост (см):")
    elif step == 'height': meas_temp['height'] = text; meas_temp['step'] = 'shoulders'; bot.send_message(user_id, "Введи Плечи (см):")
    elif step == 'shoulders': meas_temp['shoulders'] = text; meas_temp['step'] = 'chest'; bot.send_message(user_id, "Введи Грудь (см):")
    elif step == 'chest': meas_temp['chest'] = text; meas_temp['step'] = 'waist'; bot.send_message(user_id, "Введи Талию (см):")
    elif step == 'waist': meas_temp['waist'] = text; meas_temp['step'] = 'butt'; bot.send_message(user_id, "Введи Булки (см):")
    elif step == 'butt': meas_temp['butt'] = text; meas_temp['step'] = 'hips'; bot.send_message(user_id, "Введи Бедра (см):")
    elif step == 'hips':
        meas_temp['hips'] = text
        if sh:
            try:
                date_str = datetime.now().strftime("%Y-%m-%d %H:%M")
                sh.worksheet("Measurements").append_row([date_str, str(user_id), meas_temp['weight'], meas_temp['height'], meas_temp['shoulders'], meas_temp['chest'], meas_temp['waist'], meas_temp['butt'], meas_temp['hips']])
            except: pass
        bot.send_message(user_id, "✅ Замеры сохранены! Ты красотка!", reply_markup=main_keyboard(user_id))
        del meas_temp[user_id]

@bot.message_handler(func=lambda m: user_states.get(m.from_user.id) == 'waiting_progress')
def progress_input_handler(message):
    user_id = message.from_user.id
    text = message.text.strip()
    if "Отмена" in text:
        user_states[user_id] = None
        bot.send_message(message.chat.id, "Отменено.", reply_markup=main_keyboard(user_id)); return
    if sh:
        try: sh.worksheet("Progress").append_row([datetime.now().strftime("%Y-%m-%d %H:%M"), str(user_id), text])
        except: pass
    user_states[user_id] = None
    bot.send_message(message.chat.id, "✅ Твой прогресс сохранён в таблицу!", reply_markup=main_keyboard(user_id))

@bot.message_handler(func=lambda m: True)
def handle_text(message):
    text = message.text.strip()
    user_id = message.from_user.id
    
    if "Тренировка" in text or "🏋️" in text:
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("Д1 — Ноги/ягодицы", callback_data="day_Д1"))
        markup.add(types.InlineKeyboardButton("Д2 — Спина/плечи", callback_data="day_Д2"))
        bot.send_message(message.chat.id, "Выбери день тренировки:", reply_markup=markup)
        
    elif "Прогресс" in text or "📈" in text:
        markup = types.InlineKeyboardMarkup(row_width=1)
        markup.add(types.InlineKeyboardButton("📝 Записать заметку", callback_data="prog_note"))
        markup.add(types.InlineKeyboardButton("📊 Показать график веса", callback_data="prog_graph"))
        bot.send_message(message.chat.id, "Что делаем с прогрессом?", reply_markup=markup)

    elif "КБЖУ" in text or "🥗" in text:
        kbzhu_temp[user_id] = {}
        bot.send_message(message.chat.id, "🥗 **Калькулятор КБЖУ**\nВведи свой возраст (полных лет):")

    elif "Библиотека" in text or "📚" in text:
        cats = get_lib_categories()
        if not cats: bot.send_message(message.chat.id, "Библиотека пуста."); return
        markup = types.InlineKeyboardMarkup()
        for cat in cats: markup.add(types.InlineKeyboardButton(cat, callback_data=f"libcat_{cat}"))
        bot.send_message(message.chat.id, "📚 Выбери категорию:", reply_markup=markup)
        
    elif "нет сил" in text:
        markup = types.InlineKeyboardMarkup(row_width=1)
        markup.add(types.InlineKeyboardButton("➡️ Перенести", callback_data="nopower_postpone"))
        markup.add(types.InlineKeyboardButton("❌ Пропустить", callback_data="nopower_skip"))
        markup.add(types.InlineKeyboardButton("💡 Легкая версия", callback_data="day_Легкая"))
        bot.send_message(message.chat.id, "Слушай своё тело. Что будем делать?", reply_markup=markup)
        
    elif "Админ" in text and user_id == ADMIN_ID:
        url = os.environ.get('SPREADSHEET_URL')
        markup = types.InlineKeyboardMarkup(row_width=1)
        markup.add(types.InlineKeyboardButton("📊 Открыть базу данных", url=url))
        markup.add(types.InlineKeyboardButton("📣 Отправить мотивацию в канал", callback_data="admin_motivate"))
        markup.add(types.InlineKeyboardButton("🔔 Пнуть лентяев (в личку)", callback_data="admin_remind"))
        bot.send_message(message.chat.id, "👑 **Пульт управления ботом:**", parse_mode="Markdown", reply_markup=markup)
    else:
        bot.send_message(message.chat.id, "Используй кнопки 👇", reply_markup=main_keyboard(user_id))

# ================= ОБРАБОТЧИКИ КНОПОК (CALLBACK) =================
@bot.callback_query_handler(func=lambda call: True)
def callback_query(call):
    user_id = call.from_user.id
    chat_id = call.message.chat.id
    msg_id = call.message.message_id
    data = call.data

    # --- АДМИН ПАНЕЛЬ ---
    if data == "admin_motivate":
        if user_id != ADMIN_ID: return
        try:
            phrases = sh.worksheet("Motivation").col_values(1)[1:]
            if phrases: bot.send_message(CHANNEL_ID, random.choice(phrases)); bot.answer_callback_query(call.id, "✅ Отправлено в канал!")
            else: bot.answer_callback_query(call.id, "❌ В таблице нет фраз!", show_alert=True)
        except Exception as e: bot.answer_callback_query(call.id, f"Ошибка: {e}")
    elif data == "admin_remind":
        if user_id != ADMIN_ID: return
        try:
            users = sh.worksheet("Users").col_values(1)[1:]; history = sh.worksheet("History").get_all_records()
            last_workouts = {str(r.get('user_id', '')): str(r.get('date', '')) for r in history}
            sent_count = 0; now = datetime.now()
            for uid in users:
                last_w = last_workouts.get(uid); send_ping = False
                if not last_w: send_ping = True
                else:
                    try:
                        last_d = datetime.strptime(last_w, "%Y-%m-%d %H:%M")
                        if (now - last_d).days >= 3: send_ping = True
                    except: pass
                if send_ping:
                    try: bot.send_message(int(uid), "Хей! 🍑 Давно не было тренировок. Пора растрясти булочки!"); sent_count += 1
                    except: pass
            bot.answer_callback_query(call.id, f"✅ Разослано напоминаний: {sent_count}", show_alert=True)
        except Exception as e: bot.answer_callback_query(call.id, f"Ошибка: {e}")

    # --- ПРОГРЕСС ---
    elif data == "prog_note":
        user_states[user_id] = 'waiting_progress'
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True); markup.add("❌ Отмена")
        bot.send_message(chat_id, "📝 Напиши свой прогресс.", reply_markup=markup)
    elif data == "prog_graph":
        if not sh: return
        try:
            ws = sh.worksheet("Measurements"); data_rows = ws.get_all_records()
            dates, weights = [], []
            for row in data_rows:
                if str(row.get('user_id', '')) == str(user_id):
                    dates.append(row.get('date', '')[:10])
                    try: weights.append(float(row.get('weight', 0)))
                    except: pass
            if not weights: bot.answer_callback_query(call.id, "Нет данных! Сделай замеры.", show_alert=True); return
            plt.figure(figsize=(10, 5))
            plt.plot(dates, weights, marker='o', color='#FF69B4', linewidth=2, markersize=8)
            plt.title("Динамика веса (кг)", fontsize=14); plt.xlabel("Дата"); plt.ylabel("Вес"); plt.grid(True, linestyle='--', alpha=0.6); plt.xticks(rotation=45); plt.tight_layout()
            img = io.BytesIO(); plt.savefig(img, format='png', dpi=100); img.seek(0); plt.close()
            bot.send_photo(chat_id, img, caption="Твой график веса 📈🍑")
        except Exception as e: bot.answer_callback_query(call.id, f"Ошибка: {e}", show_alert=True)

    # --- ТРЕНИРОВКИ (НОВАЯ ЛОГИКА С ПОДХОДАМИ) ---
    elif data == "nopower_postpone": bot.edit_message_text("🛋 Перенесено на завтра. Отдыхай!", chat_id, msg_id)
    elif data == "nopower_skip":
        if sh:
            try: sh.worksheet("History").append_row([datetime.now().strftime("%Y-%m-%d %H:%M"), str(user_id), call.from_user.first_name, "Пропуск", "Нет сил"])
            except: pass
        bot.edit_message_text("❌ Пропущено. Записано в дневник.", chat_id, msg_id)
        
    elif data.startswith("day_"):
        day = data.replace("day_", ""); program = get_program_from_sheet(day)
        if not program: bot.answer_callback_query(call.id, f"Программа '{day}' пуста!"); return
        # Инициализируем пустой словарь выполненных подходов
        active_workouts[user_id] = {'day': day, 'program': program, 'completed_sets': {}}
        text = get_workout_text(user_id)
        bot.edit_message_text(text, chat_id, msg_id, parse_mode="Markdown", reply_markup=workout_keyboard(user_id))
        
    elif data.startswith("set_"):
        if user_id not in active_workouts: return
        parts = data.split("_")
        ex_idx = int(parts[1])
        set_idx = int(parts[2])

        completed_sets = active_workouts[user_id].get('completed_sets', {})
        if ex_idx not in completed_sets:
            completed_sets[ex_idx] = []

        if set_idx in completed_sets[ex_idx]:
            completed_sets[ex_idx].remove(set_idx) # Снять галочку
        else:
            completed_sets[ex_idx].append(set_idx) # Поставить галочку

        active_workouts[user_id]['completed_sets'] = completed_sets
        text = get_workout_text(user_id)
        bot.edit_message_text(text, chat_id, msg_id, parse_mode="Markdown", reply_markup=workout_keyboard(user_id))

    elif data == "finish":
        if user_id not in active_workouts: return
        workout = active_workouts[user_id]
        completed_sets = workout.get('completed_sets', {})
        program = workout['program']

        all_done = True
        for i in range(len(program)):
            sets_count = int(program[i].get('sets', 1))
            if len(completed_sets.get(i, [])) != sets_count:
                all_done = False
                break

        day = workout['day']
        status = "Полностью" if all_done else "Частично"
        if sh:
            try: sh.worksheet("History").append_row([datetime.now().strftime("%Y-%m-%d %H:%M"), str(user_id), call.from_user.first_name, day, status])
            except: pass
        bot.edit_message_text(f"🏁 **{day} завершена!**\nСтатус: {status}\nЗаписано в дневник! 🔥", chat_id, msg_id, parse_mode="Markdown")

    # --- БИБЛИОТЕКА ---
    elif data.startswith("libcat_"):
        cat = data.replace("libcat_", ""); exs = get_lib_exercises(cat)
        markup = types.InlineKeyboardMarkup()
        for i, ex in enumerate(exs): markup.add(types.InlineKeyboardButton(ex.get('name', 'Упр'), callback_data=f"libex_{cat}_{i}"))
        markup.add(types.InlineKeyboardButton("↩️ Назад", callback_data="lib_back"))
        bot.edit_message_text(f"📚 **Категория: {cat}**\nВыбери упражнение:", chat_id, msg_id, parse_mode="Markdown", reply_markup=markup)
    elif data.startswith("libex_"):
        parts = data.split("_"); cat, idx = parts[1], int(parts[2]); ex = get_lib_exercises(cat)[idx]
        name = ex.get('name', ''); desc = ex.get('description', ''); img = str(ex.get('image_url', '')).strip()
        text = f"🏋️ **{name}**\n\n{desc}"
        markup = types.InlineKeyboardMarkup(); markup.add(types.InlineKeyboardButton("↩️ Назад", callback_data=f"libcat_{cat}"))
        bot.delete_message(chat_id, msg_id)
        if img and img.startswith("http"):
            try: bot.send_photo(chat_id, img, caption=text, parse_mode="Markdown", reply_markup=markup)
            except: bot.send_message(chat_id, text, parse_mode="Markdown", reply_markup=markup)
        else: bot.send_message(chat_id, text, parse_mode="Markdown", reply_markup=markup)
    elif data == "lib_back":
        cats = get_lib_categories(); markup = types.InlineKeyboardMarkup()
        for c in cats: markup.add(types.InlineKeyboardButton(c, callback_data=f"libcat_{c}"))
        bot.edit_message_text("📚 Выбери категорию:", chat_id, msg_id, reply_markup=markup)

    # --- КБЖУ ---
    elif data.startswith("kbzhu_act_"):
        kbzhu_temp[user_id]['activity_val'] = float(data.split("_")[2])
        kbzhu_temp[user_id]['activity_name'] = data.split("_")[3]
        markup = types.InlineKeyboardMarkup(row_width=1)
        markup.add(types.InlineKeyboardButton("📉 Похудеть (-20%)", callback_data="kbzhu_goal_0.8_Похудеть"))
        markup.add(types.InlineKeyboardButton("⚖️ Поддержать вес", callback_data="kbzhu_goal_1.0_Поддержать"))
        markup.add(types.InlineKeyboardButton("📈 Набрать массу (+15%)", callback_data="kbzhu_goal_1.15_Набрать"))
        bot.send_message(chat_id, "Какая у тебя цель?", reply_markup=markup)
    elif data.startswith("kbzhu_goal_"):
        parts = data.split("_"); mult = float(parts[2]); goal = parts[3]
        u = kbzhu_temp[user_id]
        bmr = (10 * u['weight']) + (6.25 * u['height']) - (5 * u['age']) - 161
        tdee = int(bmr * u['activity_val'] * mult)
        p = int((tdee * 0.30) / 4); f = int((tdee * 0.30) / 9); c = int((tdee * 0.40) / 4)
        res_text = f"🥗 **Твой расчет КБЖУ** ({goal})\n\n🔥 Калории: **{tdee} ккал**\n🥩 Белки: **{p} г**\n🥑 Жиры: **{f} г**\n🍞 Углеводы: **{c} г**"
        if sh:
            try: sh.worksheet("KBZHU").append_row([datetime.now().strftime("%Y-%m-%d %H:%M"), str(user_id), u['weight'], u['height'], u['age'], u['activity_name'], tdee])
            except: pass
        bot.send_message(chat_id, res_text, parse_mode="Markdown", reply_markup=main_keyboard(user_id))
        del kbzhu_temp[user_id]

# ================= WEBHOOK И СЕРВЕР =================
@app.route('/' + TOKEN, methods=['POST'])
def webhook():
    json_str = request.get_data().decode('UTF-8')
    update = telebot.types.Update.de_json(json_str)
    bot.process_new_updates([update])
    return 'OK', 200

@app.route('/')
def index(): return "Бот работает на Render ✅"

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
