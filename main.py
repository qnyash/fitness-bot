from flask import Flask, request, jsonify
import requests
import os

app = Flask(__name__)

# Конфигурация
BOT_TOKEN = os.environ.get('BOT_TOKEN', '8609928616:AAGTJAM_ECpJ4e4BZweqsINpOtTSKO5CDMY')
ADMIN_ID = 466924747
TELEGRAM_API = f'https://api.telegram.org/bot{BOT_TOKEN}'

# ==========================================
# РАБОТА С ТАБЛИЦАМИ (Google Sheets через API)
# ==========================================
# Для простоты пока используем словари вместо Google Sheets
# Позже можно подключить Google Sheets API

users_db = {}  # {user_id: {username, first_name, state, temp_data}}
program_db = {
    'Д1': [
        {'name': 'Присед', 'sets': '4', 'reps': '10'},
        {'name': 'Выпады', 'sets': '3', 'reps': '12'},
        {'name': 'Мост', 'sets': '4', 'reps': '15'}
    ],
    'Д2': [
        {'name': 'Тяга в наклоне', 'sets': '3', 'reps': '10'},
        {'name': 'Жим лёжа', 'sets': '3', 'reps': '12'},
        {'name': 'Планка', 'sets': '3', 'reps': '45'}
    ]
}
history_db = {}  # {user_id: [{date, day, completed}]}
mood_db = {}  # {user_id: [{date, mood, energy}]}

library_db = {
    'ноги': [
        {'name': 'Присед', 'desc': 'Станьте прямо, ноги на ширине плеч. Присядьте, спина прямая.', 'img': ''}
    ],
    'ягодицы': [
        {'name': 'Мост', 'desc': 'Лежа на спине, согните ноги. Поднимайте таз вверх.', 'img': ''}
    ],
    'спина': [
        {'name': 'Тяга в наклоне', 'desc': 'Наклонитесь, спина прямая. Тяните гантели к поясу.', 'img': ''}
    ],
    'плечи': [
        {'name': 'Жим лёжа', 'desc': 'Гантели у плеч. Выжмите вверх до полного выпрямления.', 'img': ''}
    ]
}

# ==========================================
# КЛАВИАТУРЫ
# ==========================================
def main_menu_keyboard(is_admin=False):
    keyboard = [
        [{'text': '🏋️ Тренировка'}],
        [{'text': '📏 Замеры'}, {'text': '📅 История'}],
        [{'text': '🏋️‍♀️ Прогресс'}, {'text': '📚 Библиотека'}],
        [{'text': '😩 Сегодня нет сил'}]
    ]
    if is_admin:
        keyboard.append([{'text': '⚙️ Админ'}])
    return {'keyboard': keyboard, 'resize_keyboard': True}

def workout_days_inline():
    return {
        'inline_keyboard': [[
            {'text': 'Д1', 'callback_data': 'day_Д1'},
            {'text': 'Д2', 'callback_data': 'day_Д2'}
        ]]
    }

def exercises_inline(day, exercises, done_array=None):
    done = done_array or []
    buttons = []
    for i, ex in enumerate(exercises):
        is_done = i in done
        label = f"✅ {ex['name']} {ex['sets']}x{ex['reps']}" if is_done else f"☐ {ex['name']} {ex['sets']}x{ex['reps']}"
        buttons.append([{'text': label, 'callback_data': f'ex_{day}_{i}'}])
    
    buttons.append([{'text': '🏁 Завершить тренировку', 'callback_data': f'finish_{day}'}])
    return {'inline_keyboard': buttons}

def mood_inline():
    return {
        'inline_keyboard': [
            [{'text': '😍 супер', 'callback_data': 'mood_супер'}, {'text': '🙂 норм', 'callback_data': 'mood_норм'}],
            [{'text': '😐 тяжело', 'callback_data': 'mood_тяжело'}, {'text': '😵 убило', 'callback_data': 'mood_убило'}]
        ]
    }

def energy_inline():
    row = [{'text': str(i), 'callback_data': f'energy_{i}'} for i in range(1, 11)]
    return {'inline_keyboard': [row]}

def measurements_inline():
    return {
        'inline_keyboard': [
            [{'text': '➕ Ввести "Было"', 'callback_data': 'meas_before'}, {'text': '➕ Ввести "Стало"', 'callback_data': 'meas_after'}],
            [{'text': '📊 Посмотреть разницу', 'callback_data': 'meas_diff'}]
        ]
    }

def no_power_inline():
    return {
        'inline_keyboard': [
            [{'text': '➡️ Перенести', 'callback_data': 'nopower_postpone'}, {'text': '❌ Пропустить', 'callback_data': 'nopower_skip'}],
            [{'text': '💡 Легкая версия', 'callback_data': 'nopower_light'}]
        ]
    }

def admin_menu_inline():
    return {
        'inline_keyboard': [
            [{'text': '➕ Добавить упражнение', 'callback_data': 'admin_add'}],
            [{'text': '✏️ Изменить Д1', 'callback_data': 'admin_edit_Д1'}, {'text': '✏️ Изменить Д2', 'callback_data': 'admin_edit_Д2'}],
            [{'text': '🗑 Удалить упражнение', 'callback_data': 'admin_del'}],
            [{'text': '↩️ Назад', 'callback_data': 'main_menu'}]
        ]
    }

def library_categories_inline():
    cats = list(library_db.keys())
    rows = [[{'text': cat, 'callback_data': f'lib_{cat}'}] for cat in cats]
    return {'inline_keyboard': rows}

def back_inline():
    return {'inline_keyboard': [[{'text': '↩️ Назад', 'callback_data': 'main_menu'}]]}

# ==========================================
# ОТПРАВКА СООБЩЕНИЙ
# ==========================================
def send_message(chat_id, text, reply_markup=None):
    payload = {'chat_id': chat_id, 'text': text}
    if reply_markup:
        payload['reply_markup'] = reply_markup
    
    try:
        requests.post(f'{TELEGRAM_API}/sendMessage', json=payload, timeout=5)
    except Exception as e:
        print(f"Error sending message: {e}")

def edit_message_text(chat_id, message_id, text, reply_markup=None):
    payload = {'chat_id': chat_id, 'message_id': message_id, 'text': text}
    if reply_markup:
        payload['reply_markup'] = reply_markup
    
    try:
        requests.post(f'{TELEGRAM_API}/editMessageText', json=payload, timeout=5)
    except Exception as e:
        print(f"Error editing message: {e}")

def answer_callback(callback_query_id, text=''):
    try:
        requests.post(f'{TELEGRAM_API}/answerCallbackQuery', json={
            'callback_query_id': callback_query_id,
            'text': text
        }, timeout=5)
    except Exception as e:
        print(f"Error answering callback: {e}")

# ==========================================
# ОБРАБОТЧИКИ
# ==========================================
def handle_message(msg):
    chat_id = msg['chat']['id']
    user_id = msg['from']['id']
    text = msg.get('text', '')
    first_name = msg['from'].get('first_name', '')
    username = msg['from'].get('username', '')
    is_admin = (user_id == ADMIN_ID)
    
    # Создаем пользователя, если его нет
    if user_id not in users_db:
        users_db[user_id] = {
            'username': username,
            'first_name': first_name,
            'state': 'idle',
            'temp_data': {}
        }
    
    user = users_db[user_id]
    
    # Обработка команд
    if text == '/start':
        send_message(chat_id, f'Привет, {first_name}! 👋\n\nТвой фитнес-бот готов.', main_menu_keyboard(is_admin))
        return
    
    if 'Тренировка' in text or '🏋️' in text:
        send_message(chat_id, 'Выбери день тренировки:', workout_days_inline())
        return
    
    if 'Замеры' in text:
        send_message(chat_id, '📏 Замеры:', measurements_inline())
        return
    
    if 'История' in text:
        history = history_db.get(user_id, [])
        if history:
            txt = '📅 История тренировок:\n\n'
            for h in history[-5:]:  # последние 5
                status = '✅' if h['completed'] else '❌'
                txt += f"{status} {h['date']} - {h['day']}\n"
            send_message(chat_id, txt, main_menu_keyboard(is_admin))
        else:
            send_message(chat_id, '📅 История пуста. Начни тренировку!', main_menu_keyboard(is_admin))
        return
    
    if 'Прогресс' in text:
        send_message(chat_id, '🏋️‍♀️ Прогресс (в разработке)', main_menu_keyboard(is_admin))
        return
    
    if 'Библиотека' in text:
        send_message(chat_id, '📚 Библиотека:', library_categories_inline())
        return
    
    if 'Сегодня нет сил' in text or '😩' in text:
        send_message(chat_id, 'Что делаем?', no_power_inline())
        return
    
    if 'Админ' in text and is_admin:
        send_message(chat_id, '⚙️ Админ панель:', admin_menu_inline())
        return
    
    # Если пользователь в состоянии ожидания данных
    if user['state'] == 'waiting_measurements_before':
        try:
            values = text.split(',')
            if len(values) >= 6:
                save_measurements(user_id, 'before', {
                    'weight': values[0], 'waist': values[1], 'hips': values[2],
                    'chest': values[3], 'leg': values[4], 'arm': values[5]
                })
                user['state'] = 'idle'
                send_message(chat_id, '✅ Данные "Было" сохранены!', main_menu_keyboard(is_admin))
            else:
                send_message(chat_id, '❌ Формат: вес,талия,бедра,грудь,нога,рука')
        except:
            send_message(chat_id, '❌ Ошибка. Формат: вес,талия,бедра,грудь,нога,рука')
        return
    
    if user['state'] == 'waiting_measurements_after':
        try:
            values = text.split(',')
            if len(values) >= 6:
                save_measurements(user_id, 'after', {
                    'weight': values[0], 'waist': values[1], 'hips': values[2],
                    'chest': values[3], 'leg': values[4], 'arm': values[5]
                })
                user['state'] = 'idle'
                send_message(chat_id, '✅ Данные "Стало" сохранены!', main_menu_keyboard(is_admin))
            else:
                send_message(chat_id, '❌ Формат: вес,талия,бедра,грудь,нога,рука')
        except:
            send_message(chat_id, '❌ Ошибка. Формат: вес,талия,бедра,грудь,нога,рука')
        return
    
    if user['state'] == 'admin_adding':
        try:
            parts = text.split('|')
            if len(parts) >= 4:
                day, name, sets, reps = parts[0], parts[1], parts[2], parts[3]
                if day not in program_db:
                    program_db[day] = []
                program_db[day].append({'name': name, 'sets': sets, 'reps': reps})
                user['state'] = 'idle'
                send_message(chat_id, f'✅ Добавлено: {name} в {day}', main_menu_keyboard(is_admin))
            else:
                send_message(chat_id, '❌ Формат: День|Название|Подходы|Повторы')
        except:
            send_message(chat_id, '❌ Ошибка формата')
        return
    
    if user['state'] == 'admin_deleting':
        try:
            parts = text.split('|')
            if len(parts) >= 2:
                day, name = parts[0], parts[1]
                if day in program_db:
                    program_db[day] = [ex for ex in program_db[day] if ex['name'] != name]
                user['state'] = 'idle'
                send_message(chat_id, f'✅ Удалено: {name} из {day}', main_menu_keyboard(is_admin))
            else:
                send_message(chat_id, '❌ Формат: День|Название')
        except:
            send_message(chat_id, '❌ Ошибка формата')
        return
    
    # По умолчанию
    send_message(chat_id, 'Используй кнопки меню 👇', main_menu_keyboard(is_admin))

def handle_callback(query):
    callback_query_id = query['id']
    user_id = query['from']['id']
    chat_id = query['message']['chat']['id']
    message_id = query['message']['message_id']
    data = query.get('data', '')
    is_admin = (user_id == ADMIN_ID)
    
    # Создаем пользователя, если его нет
    if user_id not in users_db:
        users_db[user_id] = {'username': '', 'first_name': '', 'state': 'idle', 'temp_data': {}}
    
    user = users_db[user_id]
    
    # Отвечаем на callback
    answer_callback(callback_query_id)
    
    # Обработка callback данных
    if data.startswith('day_'):
        day = data.replace('day_', '')
        exercises = program_db.get(day, [])
        if not exercises:
            edit_message_text(chat_id, message_id, '❌ Программа пуста.')
            return
        
        user['state'] = 'workout_active'
        user['temp_data'] = {'day': day, 'done': []}
        edit_message_text(chat_id, message_id, f'🏋️ {day}\n\nОтмечай выполненные:', exercises_inline(day, exercises, []))
        return
    
    if data.startswith('ex_'):
        parts = data.split('_')
        day = parts[1]
        idx = int(parts[2])
        exercises = program_db.get(day, [])
        temp = user.get('temp_data', {})
        done = temp.get('done', [])
        
        if idx not in done:
            done.append(idx)
        
        user['temp_data'] = {'day': day, 'done': done}
        
        if len(done) >= len(exercises):
            edit_message_text(chat_id, message_id, '✅ Все выполнены!', {'inline_keyboard': []})
            save_workout(user_id, day, True)
            send_message(chat_id, '🏁 Тренировка завершена!\n\nКак самочувствие?', mood_inline())
            return
        
        caption = f'🏋️ {day}\nГотово: {len(done)}/{len(exercises)}'
        edit_message_text(chat_id, message_id, caption, exercises_inline(day, exercises, done))
        return
    
    if data.startswith('finish_'):
        day = data.replace('finish_', '')
        temp = user.get('temp_data', {})
        done = temp.get('done', [])
        exercises = program_db.get(day, [])
        
        if len(done) >= len(exercises):
            edit_message_text(chat_id, message_id, '✅ Завершено!', {'inline_keyboard': []})
            save_workout(user_id, day, True)
            send_message(chat_id, '🏁 Хорошая работа!\nКак самочувствие?', mood_inline())
        else:
            answer_callback(callback_query_id, 'Сначала отметь все!')
        return
    
    if data.startswith('mood_'):
        mood = data.replace('mood_', '')
        user['state'] = 'waiting_energy'
        user['temp_data']['mood'] = mood
        edit_message_text(chat_id, message_id, f'Настроение: {mood}\nЭнергия 1–10:', energy_inline())
        return
    
    if data.startswith('energy_'):
        energy = int(data.replace('energy_', ''))
        mood = user.get('temp_data', {}).get('mood', 'не указано')
        save_mood(user_id, mood, energy)
        user['state'] = 'idle'
        user['temp_data'] = {}
        edit_message_text(chat_id, message_id, f'✅ Сохранено: {mood}, энергия {energy}/10', main_menu_keyboard(is_admin))
        return
    
    if data == 'meas_before':
        user['state'] = 'waiting_measurements_before'
        edit_message_text(chat_id, message_id, 'Введи "Было": вес,талия,бедра,грудь,нога,рука')
        return
    
    if data == 'meas_after':
        user['state'] = 'waiting_measurements_after'
        edit_message_text(chat_id, message_id, 'Введи "Стало": вес,талия,бедра,грудь,нога,рука')
        return
    
    if data == 'meas_diff':
        edit_message_text(chat_id, message_id, '📊 Разница (в разработке)', measurements_inline())
        return
    
    if data == 'nopower_postpone':
        edit_message_text(chat_id, message_id, '➡️ Перенесено!', main_menu_keyboard(is_admin))
        return
    
    if data == 'nopower_skip':
        save_workout(user_id, 'Пропуск', False)
        edit_message_text(chat_id, message_id, '❌ Пропуск.', main_menu_keyboard(is_admin))
        return
    
    if data == 'nopower_light':
        edit_message_text(chat_id, message_id, '💡 Легкая версия:\n• Присед 2×10\n• Планка 2×30', main_menu_keyboard(is_admin))
        return
    
    if data.startswith('lib_'):
        cat = data.replace('lib_', '')
        items = library_db.get(cat, [])
        txt = f'📚 {cat.upper()}\n\n'
        for item in items:
            txt += f"• {item['name']}\n{item['desc']}\n\n"
        edit_message_text(chat_id, message_id, txt, back_inline())
        return
    
    if data == 'admin_add':
        user['state'] = 'admin_adding'
        edit_message_text(chat_id, message_id, 'Введи: День|Название|Подходы|Повторы')
        return
    
    if data == 'admin_del':
        user['state'] = 'admin_deleting'
        edit_message_text(chat_id, message_id, 'Введи: День|Название')
        return
    
    if data.startswith('admin_edit_'):
        day = data.replace('admin_edit_', '')
        if day in program_db:
            program_db[day] = []
        user['state'] = 'admin_adding'
        edit_message_text(chat_id, message_id, f'Программа {day} очищена. Введи новые упражнения:')
        return
    
    if data in ['admin_back', 'main_menu']:
        edit_message_text(chat_id, message_id, 'Главное меню', main_menu_keyboard(is_admin))
        return

# ==========================================
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ==========================================
def save_workout(user_id, day, completed):
    from datetime import datetime
    date_str = datetime.now().strftime('%d.%m.%Y')
    
    if user_id not in history_db:
        history_db[user_id] = []
    
    history_db[user_id].append({
        'date': date_str,
        'day': day,
        'completed': completed
    })

def save_mood(user_id, mood, energy):
    from datetime import datetime
    date_str = datetime.now().strftime('%d.%m.%Y')
    
    if user_id not in mood_db:
        mood_db[user_id] = []
    
    mood_db[user_id].append({
        'date': date_str,
        'mood': mood,
        'energy': energy
    })

def save_measurements(user_id, type_, values):
    # Пока просто сохраняем в память
    print(f"Measurements saved for user {user_id}: {type_} - {values}")

# ==========================================
# WEBHOOK ENDPOINT
# ==========================================
@app.route('/', methods=['POST'])
def webhook():
    try:
        update = request.get_json()
        
        if 'message' in update:
            handle_message(update['message'])
        elif 'callback_query' in update:
            handle_callback(update['callback_query'])
        
        return jsonify({'ok': True}), 200
    except Exception as e:
        print(f"Error processing update: {e}")
        return jsonify({'ok': True}), 200  # Всегда возвращаем 200

@app.route('/', methods=['GET'])
def index():
    return 'Bot is running!', 200

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))
