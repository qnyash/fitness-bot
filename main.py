import os
import json
import random
import re
import urllib.parse
import telebot
from telebot import types
from flask import Flask, request
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime

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
    scopes = [
        'https://www.googleapis.com/auth/spreadsheets',
        'https://www.googleapis.com/auth/drive'
    ]
    credentials = Credentials.from_service_account_info(creds_dict, scopes=scopes)
    gc = gspread.authorize(credentials)
    sh = gc.open_by_url(os.environ.get('SPREADSHEET_URL'))
except Exception as e:
    print("Ошибка подключения к Google Sheets:", e)


# ================= ПОЛЯ ЗАМЕРОВ =================
MEASUREMENT_FIELDS = [
    ("weight", "Вес", "кг"),
    ("height", "Рост", "см"),
    ("shoulders", "Плечи", "см"),
    ("chest", "Грудь", "см"),
    ("waist", "Талия", "см"),
    ("booty", "Булки", "см"),
    ("hips", "Бедра", "см"),
]

MEASUREMENT_LABELS = {
    "weight": "Вес",
    "height": "Рост",
    "shoulders": "Плечи",
    "chest": "Грудь",
    "waist": "Талия",
    "booty": "Булки",
    "hips": "Бедра",
}

MEASUREMENT_UNITS = {
    "weight": "кг",
    "height": "см",
    "shoulders": "см",
    "chest": "см",
    "waist": "см",
    "booty": "см",
    "hips": "см",
}


# ================= НАСТРОЙКИ КБЖУ =================
ACTIVITY_LEVELS = {
    "min": {
        "label": "Минимальная — почти нет активности",
        "coef": 1.2
    },
    "light": {
        "label": "Лёгкая — 1–2 тренировки в неделю",
        "coef": 1.375
    },
    "medium": {
        "label": "Средняя — 3–4 тренировки в неделю",
        "coef": 1.55
    },
    "high": {
        "label": "Высокая — 5–6 тренировок в неделю",
        "coef": 1.725
    },
    "very_high": {
        "label": "Очень высокая — спорт + активная работа",
        "coef": 1.9
    },
}

GOALS = {
    "loss": {
        "label": "Похудение",
        "delta": -0.15
    },
    "maintain": {
        "label": "Поддержание",
        "delta": 0
    },
    "gain": {
        "label": "Набор",
        "delta": 0.10
    },
}


# ================= ИНИЦИАЛИЗАЦИЯ ТАБЛИЦЫ =================
def init_db():
    if not sh:
        return

    worksheets = [ws.title for ws in sh.worksheets()]

    if 'Users' not in worksheets:
        ws = sh.add_worksheet(title="Users", rows=100, cols=5)
        ws.append_row(['user_id', 'name', 'date_joined'])

    if 'Program' not in worksheets:
        ws = sh.add_worksheet(title="Program", rows=100, cols=5)
        ws.append_row(['day', 'exercise', 'sets', 'reps'])

    if 'History' not in worksheets:
        ws = sh.add_worksheet(title="History", rows=100, cols=5)
        ws.append_row(['date', 'user_id', 'name', 'day', 'status'])

    if 'Progress' not in worksheets:
        ws = sh.add_worksheet(title="Progress", rows=100, cols=3)
        ws.append_row(['date', 'user_id', 'note'])

    if 'Library' not in worksheets:
        ws = sh.add_worksheet(title="Library", rows=100, cols=4)
        ws.append_row(['category', 'name', 'description', 'image_url'])

    if 'Motivation' not in worksheets:
        ws = sh.add_worksheet(title="Motivation", rows=100, cols=1)
        ws.append_row(['text'])
        ws.append_row(['Хватит откладывать! Время действовать! 🔥'])
        ws.append_row(['Каждая тренировка делает тебя лучше! 🍑'])

    if 'Measurements' not in worksheets:
        ws = sh.add_worksheet(title="Measurements", rows=200, cols=10)
        ws.append_row([
            'date',
            'user_id',
            'name',
            'weight',
            'height',
            'shoulders',
            'chest',
            'waist',
            'booty',
            'hips'
        ])

    if 'KBJU' not in worksheets:
        ws = sh.add_worksheet(title="KBJU", rows=200, cols=15)
        ws.append_row([
            'date',
            'user_id',
            'name',
            'age',
            'weight',
            'height',
            'activity_key',
            'activity_label',
            'activity_coef',
            'goal',
            'maintenance_kcal',
            'target_kcal',
            'protein_g',
            'fat_g',
            'carbs_g'
        ])


init_db()


# ================= ПАМЯТЬ БОТА =================
active_workouts = {}
user_states = {}


# ================= ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ =================
def parse_number(text):
    if not text:
        return None

    text = text.replace(",", ".")
    match = re.search(r"-?\d+(\.\d+)?", text)

    if not match:
        return None

    try:
        return float(match.group(0))
    except:
        return None


def pretty_number(value):
    try:
        value = float(value)
        if value.is_integer():
            return str(int(value))
        return str(round(value, 1))
    except:
        return str(value)


def get_program_from_sheet(day):
    if not sh:
        return []

    try:
        ws = sh.worksheet("Program")
        return [
            r for r in ws.get_all_records()
            if str(r.get('day', '')).strip() == day
        ]
    except:
        return []


def get_lib_categories():
    if not sh:
        return []

    try:
        ws = sh.worksheet("Library")
        cats = [
            str(r.get('category', '')).strip()
            for r in ws.get_all_records()
            if r.get('category')
        ]
        return list(dict.fromkeys(cats))
    except:
        return []


def get_lib_exercises(cat):
    if not sh:
        return []

    try:
        ws = sh.worksheet("Library")
        return [
            r for r in ws.get_all_records()
            if str(r.get('category', '')).strip() == cat
        ]
    except:
        return []


# ================= ЗАМЕРЫ =================
def get_user_measurements(user_id):
    if not sh:
        return []

    try:
        ws = sh.worksheet("Measurements")
        records = ws.get_all_records()
        return [
            r for r in records
            if str(r.get("user_id", "")).strip() == str(user_id)
        ]
    except:
        return []


def save_measurements(user_id, name, data):
    if not sh:
        return False

    try:
        ws = sh.worksheet("Measurements")
        ws.append_row([
            datetime.now().strftime("%Y-%m-%d %H:%M"),
            str(user_id),
            name,
            data.get("weight", ""),
            data.get("height", ""),
            data.get("shoulders", ""),
            data.get("chest", ""),
            data.get("waist", ""),
            data.get("booty", ""),
            data.get("hips", "")
        ])
        return True
    except Exception as e:
        print("Ошибка сохранения замеров:", e)
        return False


def format_last_measurements(record):
    if not record:
        return "Замеров пока нет."

    text = "📋 Последние замеры:\n\n"
    text += f"Дата: {record.get('date', '-')}\n\n"

    for key, label, unit in MEASUREMENT_FIELDS:
        value = record.get(key, "")
        if value != "":
            text += f"{label}: {pretty_number(value)} {unit}\n"

    return text


def format_measurement_diff(prev, current):
    if not prev:
        return ""

    text = "\n📊 Разница с прошлым разом:\n"

    for key, label, unit in MEASUREMENT_FIELDS:
        if key == "height":
            continue

        prev_val = parse_number(str(prev.get(key, "")))
        cur_val = parse_number(str(current.get(key, "")))

        if prev_val is None or cur_val is None:
            continue

        diff = round(cur_val - prev_val, 1)

        if diff > 0:
            text += f"{label}: +{pretty_number(diff)} {unit}\n"
        elif diff < 0:
            text += f"{label}: {pretty_number(diff)} {unit}\n"
        else:
            text += f"{label}: без изменений\n"

    return text


def send_measurement_chart(chat_id, user_id, metric):
    records = get_user_measurements(user_id)

    points = []
    labels = []

    for r in records:
        value = parse_number(str(r.get(metric, "")))
        date = str(r.get("date", ""))

        if value is not None:
            labels.append(date[5:10] if len(date) >= 10 else date)
            points.append(value)

    if len(points) < 2:
        bot.send_message(
            chat_id,
            "Для графика нужно минимум 2 записи замеров.\n\nСначала внеси замеры хотя бы два раза 📏"
        )
        return

    label = MEASUREMENT_LABELS.get(metric, metric)
    unit = MEASUREMENT_UNITS.get(metric, "")

    chart_config = {
        "type": "line",
        "data": {
            "labels": labels,
            "datasets": [{
                "label": f"{label}, {unit}",
                "data": points,
                "fill": False,
                "borderColor": "rgb(255, 99, 132)",
                "backgroundColor": "rgb(255, 99, 132)",
                "tension": 0.25
            }]
        },
        "options": {
            "title": {
                "display": True,
                "text": f"График: {label}"
            },
            "legend": {
                "display": True
            }
        }
    }

    encoded = urllib.parse.quote(json.dumps(chart_config, ensure_ascii=False))
    chart_url = f"https://quickchart.io/chart?c={encoded}"

    try:
        bot.send_photo(
            chat_id,
            chart_url,
            caption=f"📊 График: {label}"
        )
    except:
        bot.send_message(chat_id, f"📊 График: {label}\n{chart_url}")


# ================= КБЖУ =================
def calculate_kbju(age, weight, height, activity_key, goal_key):
    activity = ACTIVITY_LEVELS[activity_key]
    goal = GOALS[goal_key]

    coef = activity["coef"]

    # Формула Миффлина — Сан Жеора для женщин
    bmr = 10 * weight + 6.25 * height - 5 * age - 161

    maintenance = round(bmr * coef)
    target = round(maintenance * (1 + goal["delta"]))

    protein = round(weight * 1.8)
    fat = round(weight * 0.8)

    carbs = round((target - protein * 4 - fat * 9) / 4)
    if carbs < 0:
        carbs = 0

    return {
        "age": int(age),
        "weight": round(weight, 1),
        "height": round(height, 1),
        "activity_key": activity_key,
        "activity_label": activity["label"],
        "activity_coef": coef,
        "goal": goal["label"],
        "maintenance_kcal": maintenance,
        "target_kcal": target,
        "protein_g": protein,
        "fat_g": fat,
        "carbs_g": carbs
    }


def save_kbju_result(user_id, name, calc):
    if not sh:
        return False

    try:
        ws = sh.worksheet("KBJU")
        ws.append_row([
            datetime.now().strftime("%Y-%m-%d %H:%M"),
            str(user_id),
            name,
            calc["age"],
            calc["weight"],
            calc["height"],
            calc["activity_key"],
            calc["activity_label"],
            calc["activity_coef"],
            calc["goal"],
            calc["maintenance_kcal"],
            calc["target_kcal"],
            calc["protein_g"],
            calc["fat_g"],
            calc["carbs_g"]
        ])
        return True
    except Exception as e:
        print("Ошибка сохранения КБЖУ:", e)
        return False


def get_last_kbju(user_id):
    if not sh:
        return None

    try:
        ws = sh.worksheet("KBJU")
        records = ws.get_all_records()
        user_records = [
            r for r in records
            if str(r.get("user_id", "")).strip() == str(user_id)
        ]

        if not user_records:
            return None

        return user_records[-1]
    except:
        return None


def format_kbju_result(calc, title="🧮 Твой расчёт КБЖУ"):
    text = f"{title}\n\n"
    text += f"Возраст: {calc.get('age')} лет\n"
    text += f"Вес: {pretty_number(calc.get('weight'))} кг\n"
    text += f"Рост: {pretty_number(calc.get('height'))} см\n\n"

    text += f"Активность: {calc.get('activity_label')}\n"
    text += f"Цель: {calc.get('goal')}\n\n"

    text += f"Поддержание: {calc.get('maintenance_kcal')} ккал\n"
    text += f"Рекомендовано под цель: {calc.get('target_kcal')} ккал\n\n"

    text += f"Белки: {calc.get('protein_g')} г\n"
    text += f"Жиры: {calc.get('fat_g')} г\n"
    text += f"Углеводы: {calc.get('carbs_g')} г\n\n"

    text += "Это ориентир, не медицинское назначение 💛"

    return text


# ================= КЛАВИАТУРЫ =================
def main_keyboard(user_id):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)

    markup.row("🏋️ Тренировка")
    markup.row("📏 Замеры", "📅 История")
    markup.row("📈 Прогресс", "📚 Библиотека")
    markup.row("🧮 Калькулятор КБЖУ")
    markup.row("😩 Сегодня нет сил")

    if user_id == ADMIN_ID:
        markup.row("⚙️ Админ-панель")

    return markup


def cancel_keyboard():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add("❌ Отмена")
    return markup


def progress_inline_keyboard():
    markup = types.InlineKeyboardMarkup(row_width=1)

    markup.add(types.InlineKeyboardButton(
        "📝 Записать заметку",
        callback_data="progress_note"
    ))

    markup.add(types.InlineKeyboardButton(
        "📋 Последние замеры",
        callback_data="measurements_last"
    ))

    markup.add(types.InlineKeyboardButton(
        "📊 График веса",
        callback_data="chart_weight"
    ))

    markup.add(types.InlineKeyboardButton(
        "📊 График талии",
        callback_data="chart_waist"
    ))

    markup.add(types.InlineKeyboardButton(
        "📊 График булок",
        callback_data="chart_booty"
    ))

    markup.add(types.InlineKeyboardButton(
        "📊 График груди",
        callback_data="chart_chest"
    ))

    markup.add(types.InlineKeyboardButton(
        "📊 График плеч",
        callback_data="chart_shoulders"
    ))

    markup.add(types.InlineKeyboardButton(
        "📊 График бедер",
        callback_data="chart_hips"
    ))

    return markup


def kbju_menu_keyboard():
    markup = types.InlineKeyboardMarkup(row_width=1)

    markup.add(types.InlineKeyboardButton(
        "🧮 Рассчитать КБЖУ",
        callback_data="kbju_start"
    ))

    markup.add(types.InlineKeyboardButton(
        "📋 Последний расчёт",
        callback_data="kbju_last"
    ))

    return markup


def activity_keyboard():
    markup = types.InlineKeyboardMarkup(row_width=1)

    for key, item in ACTIVITY_LEVELS.items():
        markup.add(types.InlineKeyboardButton(
            item["label"],
            callback_data=f"kbju_activity_{key}"
        ))

    return markup


def goal_keyboard():
    markup = types.InlineKeyboardMarkup(row_width=1)

    markup.add(types.InlineKeyboardButton(
        "Похудение (-15%)",
        callback_data="kbju_goal_loss"
    ))

    markup.add(types.InlineKeyboardButton(
        "Поддержание",
        callback_data="kbju_goal_maintain"
    ))

    markup.add(types.InlineKeyboardButton(
        "Набор (+10%)",
        callback_data="kbju_goal_gain"
    ))

    return markup


def workout_keyboard(user_id):
    markup = types.InlineKeyboardMarkup(row_width=1)
    workout = active_workouts.get(user_id)

    if not workout:
        return markup

    for i, ex in enumerate(workout['program']):
        icon = "✅" if i in workout['done'] else "☐"
        name = ex.get('exercise', 'Упр')
        sets = ex.get('sets', '0')
        reps = ex.get('reps', '0')

        markup.add(types.InlineKeyboardButton(
            f"{icon} {name} ({sets}x{reps})",
            callback_data=f"ex_{i}"
        ))

    markup.add(types.InlineKeyboardButton(
        "🏁 Завершить тренировку",
        callback_data="finish"
    ))

    return markup


# ================= СТАРТ =================
@bot.message_handler(commands=['start'])
def start(message):
    user_id = message.from_user.id
    user_states[user_id] = None

    if sh:
        try:
            ws = sh.worksheet("Users")
            if str(user_id) not in ws.col_values(1):
                ws.append_row([
                    str(user_id),
                    message.from_user.first_name,
                    datetime.now().strftime("%Y-%m-%d %H:%M")
                ])
        except:
            pass

    welcome_text = f"Привет, {message.from_user.first_name}! 🤸\nГотова растрясти булочки?"

    bot.send_message(
        message.chat.id,
        welcome_text,
        reply_markup=main_keyboard(user_id)
    )


# ================= ОБРАБОТКА ТЕКСТА =================
@bot.message_handler(func=lambda m: True)
def handle_text(message):
    text = (message.text or "").strip()
    user_id = message.from_user.id
    state = user_states.get(user_id)

    # ---------- ОТМЕНА ----------
    if "Отмена" in text:
        user_states[user_id] = None
        bot.send_message(
            message.chat.id,
            "Отменено.",
            reply_markup=main_keyboard(user_id)
        )
        return

    # ---------- ВВОД ЗАМЕРОВ ----------
    if isinstance(state, dict) and state.get("mode") == "measurements":
        step = state.get("step", 0)
        data = state.get("data", {})

        value = parse_number(text)

        if value is None:
            bot.send_message(
                message.chat.id,
                "Не поняла число 😅\nВведи только цифру, например: 63.5"
            )
            return

        key, label, unit = MEASUREMENT_FIELDS[step]
        data[key] = value
        step += 1

        if step >= len(MEASUREMENT_FIELDS):
            old_records = get_user_measurements(user_id)
            prev = old_records[-1] if old_records else None

            current_record = {
                "weight": data.get("weight", ""),
                "height": data.get("height", ""),
                "shoulders": data.get("shoulders", ""),
                "chest": data.get("chest", ""),
                "waist": data.get("waist", ""),
                "booty": data.get("booty", ""),
                "hips": data.get("hips", "")
            }

            saved = save_measurements(
                user_id,
                message.from_user.first_name,
                data
            )

            user_states[user_id] = None

            if saved:
                result_text = "✅ Замеры сохранены!\n\n"
                result_text += format_last_measurements({
                    "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
                    **current_record
                })
                result_text += format_measurement_diff(prev, current_record)

                bot.send_message(
                    message.chat.id,
                    result_text,
                    reply_markup=main_keyboard(user_id)
                )
            else:
                bot.send_message(
                    message.chat.id,
                    "Не получилось сохранить замеры 😢",
                    reply_markup=main_keyboard(user_id)
                )

            return

        state["step"] = step
        state["data"] = data
        user_states[user_id] = state

        next_key, next_label, next_unit = MEASUREMENT_FIELDS[step]

        bot.send_message(
            message.chat.id,
            f"Теперь введи: {next_label} ({next_unit})"
        )
        return

    # ---------- ВВОД КБЖУ ----------
    if isinstance(state, dict) and state.get("mode") == "kbju":
        step = state.get("step")
        data = state.get("data", {})

        value = parse_number(text)

        if step == "age":
            if value is None or value < 10 or value > 100:
                bot.send_message(
                    message.chat.id,
                    "Введи возраст числом, например: 28"
                )
                return

            data["age"] = int(value)
            state["step"] = "weight"
            state["data"] = data
            user_states[user_id] = state

            bot.send_message(
                message.chat.id,
                "Теперь введи вес в кг, например: 63.5"
            )
            return

        if step == "weight":
            if value is None or value < 30 or value > 250:
                bot.send_message(
                    message.chat.id,
                    "Введи вес числом, например: 63.5"
                )
                return

            data["weight"] = value
            state["step"] = "height"
            state["data"] = data
            user_states[user_id] = state

            bot.send_message(
                message.chat.id,
                "Теперь введи рост в см, например: 168"
            )
            return

        if step == "height":
            if value is None or value < 100 or value > 230:
                bot.send_message(
                    message.chat.id,
                    "Введи рост числом в сантиметрах, например: 168"
                )
                return

            data["height"] = value
            state["step"] = "activity"
            state["data"] = data
            user_states[user_id] = state

            bot.send_message(
                message.chat.id,
                "Выбери уровень активности:",
                reply_markup=activity_keyboard()
            )
            return

        if step in ["activity", "goal"]:
            bot.send_message(
                message.chat.id,
                "Выбери вариант кнопкой ниже 👇"
            )
            return

    # ---------- ВВОД ПРОГРЕССА ----------
    if state == 'waiting_progress':
        if sh:
            try:
                sh.worksheet("Progress").append_row([
                    datetime.now().strftime("%Y-%m-%d %H:%M"),
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
        return

    # ---------- ОСНОВНОЕ МЕНЮ ----------
    if "Тренировка" in text or "🏋️" in text:
        markup = types.InlineKeyboardMarkup()

        markup.add(types.InlineKeyboardButton(
            "Д1 — Ноги/ягодицы",
            callback_data="day_Д1"
        ))

        markup.add(types.InlineKeyboardButton(
            "Д2 — Спина/плечи",
            callback_data="day_Д2"
        ))

        bot.send_message(
            message.chat.id,
            "Выбери день тренировки:",
            reply_markup=markup
        )

    elif "Замеры" in text or "📏" in text:
        user_states[user_id] = {
            "mode": "measurements",
            "step": 0,
            "data": {}
        }

        key, label, unit = MEASUREMENT_FIELDS[0]

        bot.send_message(
            message.chat.id,
            "📏 Внесём замеры тела.\n\n"
            "Я буду спрашивать по одному значению.\n"
            "Если ошиблась — нажми ❌ Отмена и начни заново.\n\n"
            f"Введи: {label} ({unit})",
            reply_markup=cancel_keyboard()
        )

    elif "Прогресс" in text or "📈" in text:
        bot.send_message(
            message.chat.id,
            "📈 Что хочешь сделать?",
            reply_markup=progress_inline_keyboard()
        )

    elif "Калькулятор" in text or "КБЖУ" in text or "🧮" in text:
        bot.send_message(
            message.chat.id,
            "🧮 Калькулятор КБЖУ\n\n"
            "Могу рассчитать норму калорий, белков, жиров и углеводов "
            "по формуле Миффлина — Сан Жеора для женщин.",
            reply_markup=kbju_menu_keyboard()
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
        markup = types.InlineKeyboardMarkup(row_width=1)

        markup.add(types.InlineKeyboardButton(
            "➡️ Перенести",
            callback_data="nopower_postpone"
        ))

        markup.add(types.InlineKeyboardButton(
            "❌ Пропустить",
            callback_data="nopower_skip"
        ))

        markup.add(types.InlineKeyboardButton(
            "💡 Легкая версия",
            callback_data="day_Легкая"
        ))

        bot.send_message(
            message.chat.id,
            "Слушай своё тело. Что будем делать?",
            reply_markup=markup
        )

    elif "Админ" in text and user_id == ADMIN_ID:
        url = os.environ.get('SPREADSHEET_URL')
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
            "👑 Пульт управления ботом:",
            reply_markup=markup
        )

    else:
        bot.send_message(
            message.chat.id,
            "Используй кнопки 👇",
            reply_markup=main_keyboard(user_id)
        )


# ================= ОБРАБОТКА INLINE-КНОПОК =================
@bot.callback_query_handler(func=lambda call: True)
def callback_query(call):
    user_id = call.from_user.id

    # ---------- КБЖУ ----------
    if call.data == "kbju_start":
        user_states[user_id] = {
            "mode": "kbju",
            "step": "age",
            "data": {}
        }

        bot.send_message(
            call.message.chat.id,
            "🧮 Рассчитаем КБЖУ.\n\n"
            "Формула только для женщин.\n"
            "Если ошиблась — нажми ❌ Отмена.\n\n"
            "Введи возраст:",
            reply_markup=cancel_keyboard()
        )

    elif call.data == "kbju_last":
        last = get_last_kbju(user_id)

        if not last:
            bot.send_message(
                call.message.chat.id,
                "У тебя пока нет сохранённых расчётов КБЖУ.\n\n"
                "Нажми 🧮 Рассчитать КБЖУ."
            )
        else:
            bot.send_message(
                call.message.chat.id,
                format_kbju_result(last, title="📋 Последний расчёт КБЖУ")
            )

    elif call.data.startswith("kbju_activity_"):
        state = user_states.get(user_id)

        if not isinstance(state, dict) or state.get("mode") != "kbju":
            bot.answer_callback_query(
                call.id,
                "Начни расчёт заново.",
                show_alert=True
            )
            return

        activity_key = call.data.replace("kbju_activity_", "")

        if activity_key not in ACTIVITY_LEVELS:
            bot.answer_callback_query(
                call.id,
                "Неизвестная активность.",
                show_alert=True
            )
            return

        state["data"]["activity_key"] = activity_key
        state["step"] = "goal"
        user_states[user_id] = state

        bot.send_message(
            call.message.chat.id,
            "Теперь выбери цель:",
            reply_markup=goal_keyboard()
        )

    elif call.data.startswith("kbju_goal_"):
        state = user_states.get(user_id)

        if not isinstance(state, dict) or state.get("mode") != "kbju":
            bot.answer_callback_query(
                call.id,
                "Начни расчёт заново.",
                show_alert=True
            )
            return

        goal_key = call.data.replace("kbju_goal_", "")

        if goal_key not in GOALS:
            bot.answer_callback_query(
                call.id,
                "Неизвестная цель.",
                show_alert=True
            )
            return

        data = state.get("data", {})
        activity_key = data.get("activity_key")

        calc = calculate_kbju(
            age=data["age"],
            weight=data["weight"],
            height=data["height"],
            activity_key=activity_key,
            goal_key=goal_key
        )

        save_kbju_result(
            user_id,
            call.from_user.first_name,
            calc
        )

        user_states[user_id] = None

        bot.send_message(
            call.message.chat.id,
            format_kbju_result(calc),
            reply_markup=main_keyboard(user_id)
        )

    # ---------- ПРОГРЕСС ----------
    elif call.data == "progress_note":
        user_states[user_id] = 'waiting_progress'

        bot.send_message(
            call.message.chat.id,
            "📝 Напиши свой прогресс.\n\n"
            "Например:\n"
            "Присед 50 кг 3х10\n"
            "Планка 1:20\n"
            "Выпады с гантелями 8 кг",
            reply_markup=cancel_keyboard()
        )

    elif call.data == "measurements_last":
        records = get_user_measurements(user_id)

        if not records:
            bot.send_message(
                call.message.chat.id,
                "Замеров пока нет. Нажми 📏 Замеры и внеси первые данные."
            )
        else:
            bot.send_message(
                call.message.chat.id,
                format_last_measurements(records[-1])
            )

    elif call.data.startswith("chart_"):
        metric = call.data.replace("chart_", "")
        send_measurement_chart(call.message.chat.id, user_id, metric)

    # ---------- АДМИН-ПАНЕЛЬ ----------
    elif call.data == "admin_motivate":
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
            bot.answer_callback_query(
                call.id,
                f"Ошибка: {e}",
                show_alert=True
            )

    elif call.data == "admin_remind":
        if user_id != ADMIN_ID:
            return

        try:
            users = sh.worksheet("Users").col_values(1)[1:]
            history = sh.worksheet("History").get_all_records()

            last_workouts = {}

            for r in history:
                uid = str(r.get('user_id', ''))
                date = str(r.get('date', ''))
                if uid:
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
            bot.answer_callback_query(
                call.id,
                f"Ошибка: {e}",
                show_alert=True
            )

    # ---------- НЕТ СИЛ ----------
    elif call.data == "nopower_postpone":
        bot.edit_message_text(
            "🛋 Перенесено на завтра. Отдыхай!",
            call.message.chat.id,
            call.message.message_id
        )

    elif call.data == "nopower_skip":
        if sh:
            try:
                sh.worksheet("History").append_row([
                    datetime.now().strftime("%Y-%m-%d %H:%M"),
                    str(user_id),
                    call.from_user.first_name,
                    "Пропуск",
                    "Нет сил"
                ])
            except:
                pass

        bot.edit_message_text(
            "❌ Пропущено. Записано в дневник.",
            call.message.chat.id,
            call.message.message_id
        )

    # ---------- ТРЕНИРОВКИ ----------
    elif call.data.startswith("day_"):
        day = call.data.replace("day_", "")
        program = get_program_from_sheet(day)

        if not program:
            bot.answer_callback_query(
                call.id,
                f"Программа '{day}' пуста!",
                show_alert=True
            )
            return

        active_workouts[user_id] = {
            'day': day,
            'program': program,
            'done': []
        }

        bot.edit_message_text(
            f"🏋️ Тренировка: {day}",
            call.message.chat.id,
            call.message.message_id,
            reply_markup=workout_keyboard(user_id)
        )

    elif call.data.startswith("ex_"):
        if user_id not in active_workouts:
            bot.answer_callback_query(
                call.id,
                "Тренировка сброшена. Начни заново.",
                show_alert=True
            )
            return

        ex_idx = int(call.data.split("_")[1])
        done = active_workouts[user_id]['done']

        if ex_idx in done:
            done.remove(ex_idx)
        else:
            done.append(ex_idx)

        day = active_workouts[user_id]['day']

        bot.edit_message_text(
            f"🏋️ Тренировка: {day}",
            call.message.chat.id,
            call.message.message_id,
            reply_markup=workout_keyboard(user_id)
        )

    elif call.data == "finish":
        if user_id not in active_workouts:
            return

        workout = active_workouts.pop(user_id)
        day = workout['day']

        status = (
            "Полностью"
            if len(workout['done']) == len(workout['program'])
            else "Частично"
        )

        if sh:
            try:
                sh.worksheet("History").append_row([
                    datetime.now().strftime("%Y-%m-%d %H:%M"),
                    str(user_id),
                    call.from_user.first_name,
                    day,
                    status
                ])
            except:
                pass

        bot.edit_message_text(
            f"🏁 {day} завершена!\n"
            f"Статус: {status}\n"
            f"Записано в дневник! 🔥",
            call.message.chat.id,
            call.message.message_id
        )

    # ---------- БИБЛИОТЕКА ----------
    elif call.data.startswith("libcat_"):
        cat = call.data.replace("libcat_", "")
        exs = get_lib_exercises(cat)

        markup = types.InlineKeyboardMarkup()

        for i, ex in enumerate(exs):
            markup.add(types.InlineKeyboardButton(
                ex.get('name', 'Упр'),
                callback_data=f"libex_{cat}_{i}"
            ))

        markup.add(types.InlineKeyboardButton(
            "↩️ Назад к категориям",
            callback_data="lib_back"
        ))

        bot.edit_message_text(
            f"📚 Категория: {cat}\nВыбери упражнение:",
            call.message.chat.id,
            call.message.message_id,
            reply_markup=markup
        )

    elif call.data.startswith("libex_"):
        parts = call.data.split("_")
        cat = parts[1]
        idx = int(parts[2])

        ex = get_lib_exercises(cat)[idx]

        name = ex.get('name', '')
        desc = ex.get('description', '')
        img = str(ex.get('image_url', '')).strip()

        text = f"🏋️ {name}\n\n{desc}"

        markup = types.InlineKeyboardMarkup()

        markup.add(types.InlineKeyboardButton(
            "↩️ Назад к списку",
            callback_data=f"libcat_{cat}"
        ))

        try:
            bot.delete_message(
                call.message.chat.id,
                call.message.message_id
            )
        except:
            pass

        if img and img.startswith("http"):
            try:
                bot.send_photo(
                    call.message.chat.id,
                    img,
                    caption=text,
                    reply_markup=markup
                )
            except:
                bot.send_message(
                    call.message.chat.id,
                    text,
                    reply_markup=markup
                )
        else:
            bot.send_message(
                call.message.chat.id,
                text,
                reply_markup=markup
            )

    elif call.data == "lib_back":
        cats = get_lib_categories()
        markup = types.InlineKeyboardMarkup()

        for c in cats:
            markup.add(types.InlineKeyboardButton(
                c,
                callback_data=f"libcat_{c}"
            ))

        bot.edit_message_text(
            "📚 Выбери категорию:",
            call.message.chat.id,
            call.message.message_id,
            reply_markup=markup
        )


# ================= WEBHOOK И СЕРВЕР =================
@app.route('/' + TOKEN, methods=['POST'])
def webhook():
    json_str = request.get_data().decode('UTF-8')
    update = telebot.types.Update.de_json(json_str)
    bot.process_new_updates([update])
    return 'OK', 200


@app.route('/')
def index():
    return "Бот работает на Render ✅"


if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 5000))
    )
