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

import matplotlib
matplotlib.use("Agg")
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
    creds_json = os.environ.get("GOOGLE_CREDENTIALS")
    creds_dict = json.loads(creds_json)

    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive"
    ]

    credentials = Credentials.from_service_account_info(creds_dict, scopes=scopes)
    gc = gspread.authorize(credentials)
    sh = gc.open_by_url(os.environ.get("SPREADSHEET_URL"))

    print("✅ Google Sheets подключен")

except Exception as e:
    print(f"❌ Ошибка подключения к Google Sheets: {e}")


def init_db():
    if not sh:
        return

    worksheets = [ws.title for ws in sh.worksheets()]

    if "Users" not in worksheets:
        ws = sh.add_worksheet(title="Users", rows=100, cols=5)
        ws.append_row(["user_id", "name", "date_joined"])

    if "Program" not in worksheets:
        ws = sh.add_worksheet(title="Program", rows=100, cols=5)
        ws.append_row(["day", "exercise", "sets", "reps"])

    if "History" not in worksheets:
        ws = sh.add_worksheet(title="History", rows=100, cols=5)
        ws.append_row(["date", "user_id", "name", "day", "status"])

    if "Progress" not in worksheets:
        ws = sh.add_worksheet(title="Progress", rows=100, cols=3)
        ws.append_row(["date", "user_id", "note"])

    if "GymWeights" not in worksheets:
        ws = sh.add_worksheet(title="GymWeights", rows=100, cols=4)
        ws.append_row(["date", "user_id", "exercise", "weight"])

    if "Library" not in worksheets:
        ws = sh.add_worksheet(title="Library", rows=100, cols=4)
        ws.append_row(["category", "name", "description", "image_url"])

    if "Motivation" not in worksheets:
        ws = sh.add_worksheet(title="Motivation", rows=100, cols=1)
        ws.append_row(["text"])

    if "Measurements" not in worksheets:
        ws = sh.add_worksheet(title="Measurements", rows=100, cols=9)
        ws.append_row([
            "date", "user_id", "weight", "height",
            "shoulders", "chest", "waist", "butt", "hips"
        ])

    if "KBZHU" not in worksheets:
        ws = sh.add_worksheet(title="KBZHU", rows=100, cols=11)
        ws.append_row([
            "date", "user_id", "weight", "height", "age",
            "activity", "calories", "goal", "protein", "fat", "carbs"
        ])
    else:
        try:
            ws = sh.worksheet("KBZHU")
            if ws.col_count < 11:
                ws.add_cols(11 - ws.col_count)

            ws.update("A1:K1", [[
                "date", "user_id", "weight", "height", "age",
                "activity", "calories", "goal", "protein", "fat", "carbs"
            ]])
        except:
            pass


init_db()


# ================= ПАМЯТЬ БОТА =================

active_workouts = {}
user_states = {}
meas_temp = {}
kbzhu_temp = {}
gym_temp = {}


# ================= ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ =================

def now_str():
    return datetime.now().strftime("%Y-%m-%d %H:%M")


def safe_int(value, default=1):
    try:
        return int(float(str(value).replace(",", ".")))
    except:
        return default


def safe_float(value, default=None):
    try:
        return float(str(value).replace(",", "."))
    except:
        return default


def is_menu_button(text):
    text = (text or "").lower()

    menu_words = [
        "тренировка",
        "замеры",
        "история",
        "прогресс",
        "кбжу",
        "калькулятор",
        "библиотека",
        "нет сил",
        "админ"
    ]

    return any(word in text for word in menu_words)


def reset_input_states(user_id):
    kbzhu_temp.pop(user_id, None)
    meas_temp.pop(user_id, None)
    gym_temp.pop(user_id, None)
    user_states[user_id] = None


def get_program_from_sheet(day):
    if not sh:
        return []

    try:
        ws = sh.worksheet("Program")
        records = ws.get_all_records()
        # Ищем точное совпадение дня (убираем пробелы)
        return [r for r in records if str(r.get("day", "")).strip() == str(day).strip()]
    except:
        return []


def get_lib_categories():
    if not sh:
        return []

    try:
        ws = sh.worksheet("Library")
        cats = []

        for r in ws.get_all_records():
            cat = str(r.get("category", "")).strip()
            if cat and cat not in cats:
                cats.append(cat)

        return cats
    except:
        return []


def get_lib_exercises(cat):
    if not sh:
        return []

    try:
        ws = sh.worksheet("Library")
        return [
            r for r in ws.get_all_records()
            if str(r.get("category", "")).strip() == str(cat).strip()
        ]
    except:
        return []


# ================= КЛАВИАТУРЫ =================

def main_keyboard(user_id):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)

    markup.add("🏋️ Тренировка")
    markup.row("📏 Замеры", "📅 История")
    markup.row("📈 Прогресс", "📚 Библиотека")
    markup.add("🧮 Калькулятор КБЖУ")
    markup.add("😩 Сегодня нет сил")

    if user_id == ADMIN_ID:
        markup.add("⚙️ Админ-панель")

    return markup


def cancel_plus_menu_keyboard(user_id):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)

    markup.add("❌ Отмена")
    markup.add("🏋️ Тренировка")
    markup.row("📏 Замеры", "📅 История")
    markup.row("📈 Прогресс", "📚 Библиотека")
    markup.add("🧮 Калькулятор КБЖУ")
    markup.add("😩 Сегодня нет сил")

    if user_id == ADMIN_ID:
        markup.add("⚙️ Админ-панель")

    return markup


# ================= ТРЕНИРОВКИ =================

def get_workout_text(user_id):
    workout = active_workouts.get(user_id)
    if not workout:
        return ""

    day_name = workout['day']
    
    # Заголовок для режима "Нет сил"
    if day_name == "СилыНет":
        return "😩 **Режим: Нет сил**\nОтмечай выполненные:"
    else:
        return f"🏋️ **Тренировка: {day_name}**\nОтмечай подходы:"


def workout_keyboard(user_id):
    markup = types.InlineKeyboardMarkup()
    workout = active_workouts.get(user_id)

    if not workout:
        return markup

    program = workout["program"]
    completed_sets = workout.get("completed_sets", {})
    
    # Проверяем режим
    is_no_power_mode = (workout['day'] == "СилыНет")

    for i, ex in enumerate(program):
        exercise_name = ex.get("exercise", "Упражнение")
        
        # Определяем состояние упражнения (выполнено или нет)
        # Для режима "Нет сил" считаем выполненным, если индекс 0 выполнен
        # Для обычной тренировки проверяем все подходы (хотя здесь мы просто генерируем кнопку одного действия)
        
        is_done = False
        
        if is_no_power_mode:
            is_done = 0 in completed_sets.get(i, [])
        else:
            sets_count = safe_int(ex.get("sets", 1), 1)
            done_count = len(completed_sets.get(i, []))
            is_done = (done_count == sets_count)

        # Текст кнопки: Галочка + Название
        label = "✅ " + exercise_name if is_done else exercise_name
        
        # Одна кнопка на упражнение
        markup.row(types.InlineKeyboardButton(
            label,
            callback_data=f"toggle_{i}"
        ))

    # Кнопки завершения
    markup.add(types.InlineKeyboardButton(
        "🏁 Завершить тренировку",
        callback_data="finish"
    ))

    return markup


# ================= START =================

@bot.message_handler(commands=["start"])
def start(message):
    user_id = message.from_user.id
    user_states[user_id] = None

    if sh:
        try:
            ws = sh.worksheet("Users")
            users = ws.col_values(1)

            if str(user_id) not in users:
                ws.append_row([
                    str(user_id),
                    message.from_user.first_name,
                    now_str()
                ])
        except:
            pass

    welcome_text = (
        f"Привет, {message.from_user.first_name}! 🍑\n"
        f"Готова растрясти булочки?"
    )

    bot.send_message(
        message.chat.id,
        welcome_text,
        reply_markup=main_keyboard(user_id)
    )


# ================= КБЖУ: ВВОД ВОЗРАСТ / РОСТ / ВЕС =================

@bot.message_handler(
    func=lambda m:
    m.from_user.id in kbzhu_temp
    and "weight" not in kbzhu_temp.get(m.from_user.id, {})
    and not is_menu_button(m.text)
)
def kbzhu_input_handler(message):
    user_id = message.from_user.id
    text = (message.text or "").strip()

    if "Отмена" in text:
        kbzhu_temp.pop(user_id, None)
        bot.send_message(
            user_id,
            "Расчёт КБЖУ отменён.",
            reply_markup=main_keyboard(user_id)
        )
        return

    u = kbzhu_temp[user_id]

    if "age" not in u:
        try:
            u["age"] = int(float(text.replace(",", ".")))
            bot.send_message(user_id, "Введи свой рост (см):")
        except:
            bot.send_message(user_id, "Пожалуйста, введи возраст числом. Например: 25")

    elif "height" not in u:
        try:
            u["height"] = float(text.replace(",", "."))
            bot.send_message(user_id, "Введи свой вес (кг):")
        except:
            bot.send_message(user_id, "Пожалуйста, введи рост числом. Например: 165")

    elif "weight" not in u:
        try:
            u["weight"] = float(text.replace(",", "."))

            markup = types.InlineKeyboardMarkup(row_width=1)
            markup.add(types.InlineKeyboardButton(
                "🛋 Сидячий",
                callback_data="kbzhu_act_1.2_Сидячий"
            ))
            markup.add(types.InlineKeyboardButton(
                "🚶 Легкая (1-3 р/н)",
                callback_data="kbzhu_act_1.375_Легкая"
            ))
            markup.add(types.InlineKeyboardButton(
                "🏋️ Средняя (3-5 р/н)",
                callback_data="kbzhu_act_1.55_Средняя"
            ))
            markup.add(types.InlineKeyboardButton(
                "🔥 Высокая (каждый день)",
                callback_data="kbzhu_act_1.725_Высокая"
            ))

            bot.send_message(
                user_id,
                "Выбери уровень активности:",
                reply_markup=markup
            )

        except:
            bot.send_message(user_id, "Пожалуйста, введи вес числом. Например: 60")


# ================= ЗАМЕРЫ =================

@bot.message_handler(
    func=lambda m:
    m.from_user.id in meas_temp
    and not is_menu_button(m.text)
)
def meas_input_handler(message):
    user_id = message.from_user.id
    text = (message.text or "").strip()

    if "Отмена" in text:
        meas_temp.pop(user_id, None)
        bot.send_message(
            user_id,
            "Замеры отменены.",
            reply_markup=main_keyboard(user_id)
        )
        return

    step = meas_temp.get(user_id, {}).get("step", "")

    if step == "weight":
        meas_temp[user_id]["weight"] = text
        meas_temp[user_id]["step"] = "height"
        bot.send_message(user_id, "Введи Рост (см):")

    elif step == "height":
        meas_temp[user_id]["height"] = text
        meas_temp[user_id]["step"] = "shoulders"
        bot.send_message(user_id, "Введи Плечи (см):")

    elif step == "shoulders":
        meas_temp[user_id]["shoulders"] = text
        meas_temp[user_id]["step"] = "chest"
        bot.send_message(user_id, "Введи Грудь (см):")

    elif step == "chest":
        meas_temp[user_id]["chest"] = text
        meas_temp[user_id]["step"] = "waist"
        bot.send_message(user_id, "Введи Талию (см):")

    elif step == "waist":
        meas_temp[user_id]["waist"] = text
        meas_temp[user_id]["step"] = "butt"
        bot.send_message(user_id, "Введи Булки (см):")

    elif step == "butt":
        meas_temp[user_id]["butt"] = text
        meas_temp[user_id]["step"] = "hips"
        bot.send_message(user_id, "Введи Бедра (см):")

    elif step == "hips":
        meas_temp[user_id]["hips"] = text

        if sh:
            try:
                m = meas_temp[user_id]
                sh.worksheet("Measurements").append_row([
                    now_str(),
                    str(user_id),
                    m["weight"],
                    m["height"],
                    m["shoulders"],
                    m["chest"],
                    m["waist"],
                    m["butt"],
                    m["hips"]
                ])
            except:
                pass

        meas_temp.pop(user_id, None)

        bot.send_message(
            user_id,
            "✅ Замеры сохранены! Ты красотка!",
            reply_markup=main_keyboard(user_id)
        )


# ================= ПРОГРЕСС: ЗАМЕТКА =================

@bot.message_handler(
    func=lambda m:
    user_states.get(m.from_user.id) == "waiting_progress"
    and not is_menu_button(m.text)
)
def progress_input_handler(message):
    user_id = message.from_user.id
    text = (message.text or "").strip()

    if "Отмена" in text:
        user_states[user_id] = None
        bot.send_message(
            message.chat.id,
            "Отменено.",
            reply_markup=main_keyboard(user_id)
        )
        return

    if sh:
        try:
            sh.worksheet("Progress").append_row([
                now_str(),
                str(user_id),
                text
            ])
        except:
            pass

    user_states[user_id] = None

    bot.send_message(
        message.chat.id,
        "✅ Твой прогресс сохранён в таблицу!",
        reply_markup=main_keyboard(user_id)
    )


# ================= РАБОЧИЕ ВЕСА В ЗАЛЕ =================

@bot.message_handler(
    func=lambda m:
    m.from_user.id in gym_temp
    and not is_menu_button(m.text)
)
def gym_weight_input_handler(message):
    user_id = message.from_user.id
    text = (message.text or "").strip()

    if "Отмена" in text:
        gym_temp.pop(user_id, None)
        bot.send_message(
            message.chat.id,
            "Отменено.",
            reply_markup=main_keyboard(user_id)
        )
        return

    temp = gym_temp.get(user_id, {})
    mode = temp.get("mode")
    step = temp.get("step")

    if mode == "add":
        if step == "exercise":
            temp["exercise"] = text
            temp["step"] = "weight"
            gym_temp[user_id] = temp

            bot.send_message(
                message.chat.id,
                "Введи рабочий вес числом.\nНапример: `45` или `45.5`",
                parse_mode="Markdown"
            )
            return

        elif step == "weight":
            weight = safe_float(text, None)

            if weight is None:
                bot.send_message(
                    message.chat.id,
                    "Введи вес числом. Например: 45"
                )
                return

            if sh:
                try:
                    sh.worksheet("GymWeights").append_row([
                        now_str(),
                        str(user_id),
                        temp.get("exercise", ""),
                        weight
                    ])
                except:
                    pass

            gym_temp.pop(user_id, None)

            bot.send_message(
                message.chat.id,
                f"✅ Рабочий вес сохранён:\n"
                f"{temp.get('exercise', '')} — {weight} кг",
                reply_markup=main_keyboard(user_id)
            )
            return

    elif mode == "graph":
        exercise_name = text.strip()

        if not sh:
            gym_temp.pop(user_id, None)
            bot.send_message(
                message.chat.id,
                "Таблица недоступна.",
                reply_markup=main_keyboard(user_id)
            )
            return

        try:
            rows = sh.worksheet("GymWeights").get_all_records()

            dates = []
            weights = []

            for row in rows:
                row_user = str(row.get("user_id", ""))
                row_ex = str(row.get("exercise", "")).strip().lower()

                if row_user == str(user_id) and row_ex == exercise_name.lower():
                    w = safe_float(row.get("weight"), None)

                    if w is not None:
                        dates.append(str(row.get("date", ""))[:10])
                        weights.append(w)

            if not weights:
                gym_temp.pop(user_id, None)
                bot.send_message(
                    message.chat.id,
                    f"По упражнению `{exercise_name}` пока нет данных.\n"
                    f"Сначала добавь рабочий вес через кнопку "
                    f"«➕ Записать рабочий вес».",
                    parse_mode="Markdown",
                    reply_markup=main_keyboard(user_id)
                )
                return

            plt.figure(figsize=(10, 5))
            plt.plot(
                dates,
                weights,
                marker="o",
                color="#8A2BE2",
                linewidth=2,
                markersize=8
            )

            plt.title(f"Рабочий вес: {exercise_name}", fontsize=14)
            plt.xlabel("Дата")
            plt.ylabel("Вес, кг")
            plt.grid(True, linestyle="--", alpha=0.6)
            plt.xticks(rotation=45)
            plt.tight_layout()

            img = io.BytesIO()
            plt.savefig(img, format="png", dpi=100)
            img.seek(0)
            plt.close()

            gym_temp.pop(user_id, None)

            bot.send_photo(
                message.chat.id,
                img,
                caption=f"🏋️ График рабочих весов: {exercise_name}",
                reply_markup=main_keyboard(user_id)
            )

        except Exception as e:
            gym_temp.pop(user_id, None)
            bot.send_message(
                message.chat.id,
                f"Ошибка построения графика: {e}",
                reply_markup=main_keyboard(user_id)
            )


# ================= ОСНОВНОЕ МЕНЮ =================

@bot.message_handler(func=lambda m: True)
def handle_text(message):
    text = (message.text or "").strip()
    user_id = message.from_user.id

    if is_menu_button(text):
        reset_input_states(user_id)

    if "Тренировка" in text or "🏋️" in text:
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton(
            "Д1",
            callback_data="day_Д1"
        ))
        markup.add(types.InlineKeyboardButton(
            "Д2",
            callback_data="day_Д2"
        ))

        bot.send_message(
            message.chat.id,
            "Выбери день тренировки:",
            reply_markup=markup
        )

    elif "Замеры" in text or "📏" in text:
        meas_temp[user_id] = {"step": "weight"}

        bot.send_message(
            message.chat.id,
            "Начинаем замеры! 📏\nВведи Вес (кг):",
            reply_markup=main_keyboard(user_id)
        )

    elif "История" in text or "📅" in text:
        if not sh:
            bot.send_message(message.chat.id, "История недоступна.")
            return

        try:
            rows = sh.worksheet("History").get_all_records()
            user_rows = [
                r for r in rows
                if str(r.get("user_id", "")) == str(user_id)
            ][-10:]

            if not user_rows:
                bot.send_message(
                    message.chat.id,
                    "История пока пустая.",
                    reply_markup=main_keyboard(user_id)
                )
                return

            msg = "📅 **Твоя история тренировок:**\n\n"

            for r in reversed(user_rows):
                msg += (
                    f"• {r.get('date', '—')} — "
                    f"{r.get('day', '—')} "
                    f"({r.get('status', '—')})\n"
                )

            bot.send_message(
                message.chat.id,
                msg,
                parse_mode="Markdown",
                reply_markup=main_keyboard(user_id)
            )

        except:
            bot.send_message(message.chat.id, "Не смогла загрузить историю 😢")

    elif "Прогресс" in text or "📈" in text:
        markup = types.InlineKeyboardMarkup(row_width=1)

        markup.add(types.InlineKeyboardButton(
            "📝 Записать заметку",
            callback_data="prog_note"
        ))

        markup.add(types.InlineKeyboardButton(
            "📊 График веса тела",
            callback_data="prog_graph_weight"
        ))

        markup.add(types.InlineKeyboardButton(
            "📏 Графики параметров",
            callback_data="prog_params"
        ))

        markup.add(types.InlineKeyboardButton(
            "➕ Записать рабочий вес",
            callback_data="gym_add"
        ))

        markup.add(types.InlineKeyboardButton(
            "🏋️ График рабочих весов",
            callback_data="gym_graph"
        ))

        bot.send_message(
            message.chat.id,
            "📈 Что смотрим по прогрессу?",
            reply_markup=markup
        )

    elif "КБЖУ" in text or "🥗" in text or "🧮" in text or "Калькулятор" in text:
        markup = types.InlineKeyboardMarkup(row_width=1)
        markup.add(types.InlineKeyboardButton(
            "➕ Новый расчёт",
            callback_data="kbzhu_new"
        ))
        markup.add(types.InlineKeyboardButton(
            "📄 Посмотреть предыдущий расчёт",
            callback_data="kbzhu_last"
        ))

        bot.send_message(
            message.chat.id,
            "🧮 **Калькулятор КБЖУ**\nЧто хочешь сделать?",
            parse_mode="Markdown",
            reply_markup=markup
        )

    elif "Библиотека" in text or "📚" in text:
        cats = get_lib_categories()

        if not cats:
            bot.send_message(
                message.chat.id,
                "Библиотека пуста. Добавь данные в таблицу!"
            )
            return

        markup = types.InlineKeyboardMarkup()

        for cat in cats:
            markup.add(types.InlineKeyboardButton(
                cat,
                callback_data=f"libcat_{cat}"
            ))

        bot.send_message(
            message.chat.id,
            "📚 Выбери категорию:",
            reply_markup=markup
        )

    elif "нет сил" in text:
        # Показываем меню выбора действий
        markup = types.InlineKeyboardMarkup(row_width=1)
        markup.add(types.InlineKeyboardButton(
            "💡 Режим: Нет сил (Легкая версия)",
            callback_data="day_СилыНет"
        ))
        markup.add(types.InlineKeyboardButton(
            "➡️ Перенести",
            callback_data="nopower_postpone"
        ))
        markup.add(types.InlineKeyboardButton(
            "❌ Пропустить",
            callback_data="nopower_skip"
        ))

        bot.send_message(
            message.chat.id,
            "😩 Слушай своё тело. Что будем делать?",
            reply_markup=markup
        )

    elif "Админ" in text and user_id == ADMIN_ID:
        url = os.environ.get("SPREADSHEET_URL")

        markup = types.InlineKeyboardMarkup(row_width=1)
        markup.add(types.InlineKeyboardButton(
            "📊 Открыть базу данных",
            url=url
        ))
        markup.add(types.InlineKeyboardButton(
            "📣 Отправить мотивацию в канал",
            callback_data="admin_motivate"
        ))
        markup.add(types.InlineKeyboardButton(
            "🔔 Пнуть лентяев (в личку)",
            callback_data="admin_remind"
        ))

        bot.send_message(
            message.chat.id,
            "👑 **Пульт управления ботом:**",
            parse_mode="Markdown",
            reply_markup=markup
        )

    else:
        bot.send_message(
            message.chat.id,
            "Используй кнопки 👇",
            reply_markup=main_keyboard(user_id)
        )


# ================= CALLBACK-КНОПКИ =================

@bot.callback_query_handler(func=lambda call: True)
def callback_query(call):
    user_id = call.from_user.id
    chat_id = call.message.chat.id
    msg_id = call.message.message_id
    data = call.data

    # ---------- АДМИН-ПАНЕЛЬ ----------

    if data == "admin_motivate":
        if user_id != ADMIN_ID:
            return

        try:
            phrases = sh.worksheet("Motivation").col_values(1)[1:]

            if phrases:
                bot.send_message(CHANNEL_ID, random.choice(phrases))
                bot.answer_callback_query(call.id, "✅ Отправлено в канал!")
            else:
                bot.answer_callback_query(
                    call.id,
                    "❌ В таблице нет фраз!",
                    show_alert=True
                )

        except Exception as e:
            bot.answer_callback_query(call.id, f"Ошибка: {e}", show_alert=True)

    elif data == "admin_remind":
        if user_id != ADMIN_ID:
            return

        try:
            users = sh.worksheet("Users").col_values(1)[1:]
            history = sh.worksheet("History").get_all_records()

            last_workouts = {}

            for r in history:
                uid = str(r.get("user_id", ""))
                date = str(r.get("date", ""))
                if uid and date:
                    last_workouts[uid] = date

            sent_count = 0
            now = datetime.now()

            for uid in users:
                last_w = last_workouts.get(uid)
                send_ping = False

                if not last_w:
                    send_ping = True
                else:
                    try:
                        last_d = datetime.strptime(last_w, "%Y-%m-%d %H:%M")
                        if (now - last_d).days >= 3:
                            send_ping = True
                    except:
                        pass

                if send_ping:
                    try:
                        bot.send_message(
                            int(uid),
                            "Хей! 🍑 Давно не было тренировок. Пора растрясти булочки!"
                        )
                        sent_count += 1
                    except:
                        pass

            bot.answer_callback_query(
                call.id,
                f"✅ Разослано напоминаний: {sent_count}",
                show_alert=True
            )

        except Exception as e:
            bot.answer_callback_query(call.id, f"Ошибка: {e}", show_alert=True)


    # ---------- ПРОГРЕСС ----------

    elif data == "prog_note":
        user_states[user_id] = "waiting_progress"

        bot.send_message(
            chat_id,
            "📝 Напиши свой прогресс.\nНапример: `Присед 50 кг 3х10`",
            parse_mode="Markdown",
            reply_markup=cancel_plus_menu_keyboard(user_id)
        )

    elif data in ["prog_graph", "prog_graph_weight"]:
        if not sh:
            return

        try:
            ws = sh.worksheet("Measurements")
            rows = ws.get_all_records()

            dates = []
            weights = []

            for row in rows:
                if str(row.get("user_id", "")) == str(user_id):
                    w = safe_float(row.get("weight"), None)

                    if w is not None:
                        dates.append(str(row.get("date", ""))[:10])
                        weights.append(w)

            if not weights:
                bot.answer_callback_query(
                    call.id,
                    "Нет данных! Сделай замеры.",
                    show_alert=True
                )
                return

            plt.figure(figsize=(10, 5))
            plt.plot(
                dates,
                weights,
                marker="o",
                color="#FF69B4",
                linewidth=2,
                markersize=8
            )
            plt.title("Динамика веса тела (кг)", fontsize=14)
            plt.xlabel("Дата")
            plt.ylabel("Вес")
            plt.grid(True, linestyle="--", alpha=0.6)
            plt.xticks(rotation=45)
            plt.tight_layout()

            img = io.BytesIO()
            plt.savefig(img, format="png", dpi=100)
            img.seek(0)
            plt.close()

            bot.send_photo(chat_id, img, caption="📊 Твой график веса тела 📈🍑")

        except Exception as e:
            bot.answer_callback_query(
                call.id,
                f"Ошибка: {e}",
                show_alert=True
            )

    elif data == "prog_params":
        markup = types.InlineKeyboardMarkup(row_width=1)

        markup.add(types.InlineKeyboardButton(
            "⚖️ Вес тела",
            callback_data="param_weight"
        ))
        markup.add(types.InlineKeyboardButton(
            "📏 Плечи",
            callback_data="param_shoulders"
        ))
        markup.add(types.InlineKeyboardButton(
            "🍒 Грудь",
            callback_data="param_chest"
        ))
        markup.add(types.InlineKeyboardButton(
            "⌛ Талия",
            callback_data="param_waist"
        ))
        markup.add(types.InlineKeyboardButton(
            "🍑 Булки",
            callback_data="param_butt"
        ))
        markup.add(types.InlineKeyboardButton(
            "🦵 Бёдра",
            callback_data="param_hips"
        ))

        bot.edit_message_text(
            "📏 Выбери параметр для графика:",
            chat_id,
            msg_id,
            reply_markup=markup
        )

    elif data.startswith("param_"):
        if not sh:
            return

        param = data.replace("param_", "")

        param_titles = {
            "weight": ("Вес тела", "кг", "#FF69B4"),
            "shoulders": ("Плечи", "см", "#1E90FF"),
            "chest": ("Грудь", "см", "#FF1493"),
            "waist": ("Талия", "см", "#32CD32"),
            "butt": ("Булки", "см", "#FF8C00"),
            "hips": ("Бёдра", "см", "#8A2BE2")
        }

        title, unit, color = param_titles.get(param, ("Параметр", "", "#FF69B4"))

        try:
            rows = sh.worksheet("Measurements").get_all_records()

            dates = []
            values = []

            for row in rows:
                if str(row.get("user_id", "")) == str(user_id):
                    val = safe_float(row.get(param), None)

                    if val is not None:
                        dates.append(str(row.get("date", ""))[:10])
                        values.append(val)

            if not values:
                bot.answer_callback_query(
                    call.id,
                    f"Нет данных для графика: {title}",
                    show_alert=True
                )
                return

            plt.figure(figsize=(10, 5))
            plt.plot(
                dates,
                values,
                marker="o",
                color=color,
                linewidth=2,
                markersize=8
            )

            plt.title(f"Динамика: {title}", fontsize=14)
            plt.xlabel("Дата")
            plt.ylabel(unit)
            plt.grid(True, linestyle="--", alpha=0.6)
            plt.xticks(rotation=45)
            plt.tight_layout()

            img = io.BytesIO()
            plt.savefig(img, format="png", dpi=100)
            img.seek(0)
            plt.close()

            bot.send_photo(
                chat_id,
                img,
                caption=f"📈 График: {title}"
            )

        except Exception as e:
            bot.answer_callback_query(
                call.id,
                f"Ошибка: {e}",
                show_alert=True
            )

    elif data == "gym_add":
        gym_temp[user_id] = {
            "mode": "add",
            "step": "exercise"
        }

        bot.send_message(
            chat_id,
            "🏋️ Введи название упражнения.\nНапример: `Жим ногами`",
            parse_mode="Markdown",
            reply_markup=cancel_plus_menu_keyboard(user_id)
        )

    elif data == "gym_graph":
        gym_temp[user_id] = {
            "mode": "graph",
            "step": "exercise"
        }

        bot.send_message(
            chat_id,
            "🏋️ Введи название упражнения, по которому построить график.\nНапример: `Жим ногами`",
            parse_mode="Markdown",
            reply_markup=cancel_plus_menu_keyboard(user_id)
        )


    # ---------- КБЖУ ----------

    elif data == "kbzhu_new":
        kbzhu_temp[user_id] = {}

        bot.edit_message_text(
            "🥗 **Калькулятор КБЖУ**\nВведи свой возраст (полных лет):",
            chat_id,
            msg_id,
            parse_mode="Markdown"
        )

    elif data == "kbzhu_last":
        if not sh:
            bot.answer_callback_query(
                call.id,
                "Таблица не подключена",
                show_alert=True
            )
            return

        try:
            rows = sh.worksheet("KBZHU").get_all_records()
            last = None

            for row in reversed(rows):
                if str(row.get("user_id", "")) == str(user_id):
                    last = row
                    break

            if not last:
                bot.answer_callback_query(
                    call.id,
                    "У тебя пока нет предыдущих расчётов.",
                    show_alert=True
                )
                return

            calories_raw = str(last.get("calories", "0")).replace(",", ".")
            calories = int(float(calories_raw)) if calories_raw else 0

            protein = last.get("protein") or int((calories * 0.30) / 4)
            fat = last.get("fat") or int((calories * 0.30) / 9)
            carbs = last.get("carbs") or int((calories * 0.40) / 4)

            msg = (
                f"📄 **Предыдущий расчёт КБЖУ**\n\n"
                f"📅 Дата: {last.get('date', '—')}\n"
                f"🎯 Цель: {last.get('goal', '—')}\n"
                f"⚙️ Активность: {last.get('activity', '—')}\n\n"
                f"🔥 Калории: **{calories} ккал**\n"
                f"🥩 Белки: **{protein} г**\n"
                f"🥑 Жиры: **{fat} г**\n"
                f"🍞 Углеводы: **{carbs} г**\n\n"
                f"Данные расчёта:\n"
                f"Вес: {last.get('weight', '—')} кг\n"
                f"Рост: {last.get('height', '—')} см\n"
                f"Возраст: {last.get('age', '—')}"
            )

            bot.send_message(
                chat_id,
                msg,
                parse_mode="Markdown",
                reply_markup=main_keyboard(user_id)
            )

        except Exception as e:
            bot.answer_callback_query(
                call.id,
                f"Ошибка: {e}",
                show_alert=True
            )

    elif data.startswith("kbzhu_act_"):
        if user_id not in kbzhu_temp:
            bot.answer_callback_query(
                call.id,
                "Начни расчёт заново.",
                show_alert=True
            )
            return

        parts = data.split("_")

        kbzhu_temp[user_id]["activity_val"] = float(parts[2])
        kbzhu_temp[user_id]["activity_name"] = parts[3]

        markup = types.InlineKeyboardMarkup(row_width=1)
        markup.add(types.InlineKeyboardButton(
            "📉 Похудеть (-20%)",
            callback_data="kbzhu_goal_0.8_Похудеть"
        ))
        markup.add(types.InlineKeyboardButton(
            "⚖️ Поддержать вес",
            callback_data="kbzhu_goal_1.0_Поддержать"
        ))
        markup.add(types.InlineKeyboardButton(
            "📈 Набрать массу (+15%)",
            callback_data="kbzhu_goal_1.15_Набрать"
        ))

        bot.send_message(
            chat_id,
            "Какая у тебя цель?",
            reply_markup=markup
        )

    elif data.startswith("kbzhu_goal_"):
        if user_id not in kbzhu_temp:
            bot.answer_callback_query(
                call.id,
                "Начни расчёт заново.",
                show_alert=True
            )
            return

        parts = data.split("_")
        mult = float(parts[2])
        goal = parts[3]

        u = kbzhu_temp[user_id]

        bmr = (
            (10 * u["weight"])
            + (6.25 * u["height"])
            - (5 * u["age"])
            - 161
        )

        tdee = int(bmr * u["activity_val"] * mult)

        protein = int((tdee * 0.30) / 4)
        fat = int((tdee * 0.30) / 9)
        carbs = int((tdee * 0.40) / 4)

        res_text = (
            f"🥗 **Твой расчёт КБЖУ** ({goal})\n\n"
            f"🔥 Калории: **{tdee} ккал**\n"
            f"🥩 Белки: **{protein} г**\n"
            f"🥑 Жиры: **{fat} г**\n"
            f"🍞 Углеводы: **{carbs} г**"
        )

        if sh:
            try:
                sh.worksheet("KBZHU").append_row([
                    now_str(),
                    str(user_id),
                    u["weight"],
                    u["height"],
                    u["age"],
                    u["activity_name"],
                    tdee,
                    goal,
                    protein,
                    fat,
                    carbs
                ])
            except:
                pass

        kbzhu_temp.pop(user_id, None)

        bot.send_message(
            chat_id,
            res_text,
            parse_mode="Markdown",
            reply_markup=main_keyboard(user_id)
        )


    # ---------- НЕТ СИЛ (ДЕЙСТВИЯ) ----------
    
    elif data == "nopower_postpone":
        if sh:
            try:
                sh.worksheet("History").append_row([
                    now_str(),
                    str(user_id),
                    call.from_user.first_name,
                    "Перенос",
                    "Нет сил"
                ])
            except:
                pass
        bot.edit_message_text(
            "➡️ Тренировка перенесена на завтра.",
            chat_id,
            msg_id
        )

    elif data == "nopower_skip":
        if sh:
            try:
                sh.worksheet("History").append_row([
                    now_str(),
                    str(user_id),
                    call.from_user.first_name,
                    "Пропуск",
                    "Нет сил"
                ])
            except:
                pass
        bot.edit_message_text(
            "❌ Тренировка пропущена.",
            chat_id,
            msg_id
        )


    # ---------- ТРЕНИРОВКИ (ВКЛ. РЕЖИМ НЕТ СИЛ) ----------

    elif data.startswith("day_"):
        day = data.replace("day_", "")
        program = get_program_from_sheet(day)

        if not program:
            bot.answer_callback_query(
                call.id,
                f"Программа '{day}' пуста!",
                show_alert=True
            )
            return

        active_workouts[user_id] = {
            "day": day,
            "program": program,
            "completed_sets": {}
        }

        bot.edit_message_text(
            get_workout_text(user_id),
            chat_id,
            msg_id,
            parse_mode="Markdown",
            reply_markup=workout_keyboard(user_id)
        )

    elif data.startswith("toggle_"):
        # Обработка переключения галочки для упражнения
        if user_id not in active_workouts:
            return

        ex_idx = int(data.split("_")[1])
        completed_sets = active_workouts[user_id].get("completed_sets", {})

        # Если упражнение еще не отмечено
        if ex_idx not in completed_sets:
            completed_sets[ex_idx] = [0] # Помечаем как выполненное (флаг 0)
        else:
            # Если уже отмечено, удаляем отметку
            if 0 in completed_sets[ex_idx]:
                del completed_sets[ex_idx]

        active_workouts[user_id]["completed_sets"] = completed_sets

        bot.edit_message_text(
            get_workout_text(user_id),
            chat_id,
            msg_id,
            parse_mode="Markdown",
            reply_markup=workout_keyboard(user_id)
        )

    elif data == "finish":
        if user_id not in active_workouts:
            return

        workout = active_workouts.pop(user_id)
        completed_sets = workout.get("completed_sets", {})
        program = workout["program"]
        day_name = workout["day"]
        
        all_done = True
        is_no_power_mode = (day_name == "СилыНет")

        for i in range(len(program)):
            if is_no_power_mode:
                # В режиме "нет сил" проверяем наличие флага 0
                if i not in completed_sets:
                    all_done = False
            else:
                # Для обычных тренировок проверяем количество подходов (если нужно)
                # Сейчас в обычной логике тоже одна кнопка, так что проверяем наличие ключа
                if i not in completed_sets:
                    all_done = False
            
            if not all_done:
                break

        status = "Полностью" if all_done else "Частично"

        if sh:
            try:
                sh.worksheet("History").append_row([
                    now_str(),
                    str(user_id),
                    call.from_user.first_name,
                    day_name,
                    status
                ])
            except:
                pass

        bot.edit_message_text(
            f"🏁 **{day_name} завершена!**\n"
            f"Статус: {status}\n"
            f"Записано в дневник! 🔥",
            chat_id,
            msg_id,
            parse_mode="Markdown"
        )


    # ---------- БИБЛИОТЕКА ----------

    elif data.startswith("libcat_"):
        cat = data.replace("libcat_", "")
        exercises = get_lib_exercises(cat)

        markup = types.InlineKeyboardMarkup()

        for i, ex in enumerate(exercises):
            markup.add(types.InlineKeyboardButton(
                ex.get("name", "Упражнение"),
                callback_data=f"libex_{cat}_{i}"
            ))

        markup.add(types.InlineKeyboardButton(
            "↩️ Назад",
            callback_data="lib_back"
        ))

        bot.edit_message_text(
            f"📚 **Категория: {cat}**\nВыбери упражнение:",
            chat_id,
            msg_id,
            parse_mode="Markdown",
            reply_markup=markup
        )

    elif data.startswith("libex_"):
        parts = data.split("_")
        cat = parts[1]
        idx = int(parts[2])

        exercises = get_lib_exercises(cat)
        ex = exercises[idx]

        name = ex.get("name", "")
        desc = ex.get("description", "")
        img = str(ex.get("image_url", "")).strip()

        text = f"🏋️ **{name}**\n\n{desc}"

        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton(
            "↩️ Назад",
            callback_data=f"libcat_{cat}"
        ))

        try:
            bot.delete_message(chat_id, msg_id)
        except:
            pass

        if img and img.startswith("http"):
            try:
                bot.send_photo(
                    chat_id,
                    img,
                    caption=text,
                    parse_mode="Markdown",
                    reply_markup=markup
                )
            except:
                bot.send_message(
                    chat_id,
                    text,
                    parse_mode="Markdown",
                    reply_markup=markup
                )
        else:
            bot.send_message(
                chat_id,
                text,
                parse_mode="Markdown",
                reply_markup=markup
            )

    elif data == "lib_back":
        cats = get_lib_categories()
        markup = types.InlineKeyboardMarkup()

        for c in cats:
            markup.add(types.InlineKeyboardButton(
                c,
                callback_data=f"libcat_{c}"
            ))

        bot.edit_message_text(
            "📚 Выбери категорию:",
            chat_id,
            msg_id,
            reply_markup=markup
        )


# ================= WEBHOOK И СЕРВЕР =================

@app.route("/" + TOKEN, methods=["POST"])
def webhook():
    json_str = request.get_data().decode("UTF-8")
    update = telebot.types.Update.de_json(json_str)
    bot.process_new_updates([update])
    return "OK", 200


@app.route("/")
def index():
    return "Бот работает на Render ✅"


if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 5000))
    )
