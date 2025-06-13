# database.py
import sqlite3
from datetime import datetime, date, time

DATABASE_FILE = 'health_assistant.db'

def get_db_connection():
    """Retorna uma conexão com o banco de dados SQLite."""
    conn = sqlite3.connect(DATABASE_FILE)
    conn.row_factory = sqlite3.Row # Para acessar colunas por nome
    return conn

def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()

    # Tabela de usuários
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            whatsapp_number TEXT UNIQUE NOT NULL,
            last_interaction_date DATE DEFAULT CURRENT_DATE
        )
    ''')

    # Tabela food_entries (já modificada para macronutrientes)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS food_entries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            foods_description TEXT NOT NULL,
            calories REAL NOT NULL,
            carbohydrates REAL DEFAULT 0,
            proteins REAL DEFAULT 0,
            fats REAL DEFAULT 0,
            entry_date DATE DEFAULT CURRENT_DATE,
            entry_time TIME DEFAULT CURRENT_TIME,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS weight_entries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            weight REAL NOT NULL,
            entry_date DATE DEFAULT CURRENT_DATE,
            entry_time TIME DEFAULT CURRENT_TIME,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS exercise_entries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            activity_name TEXT NOT NULL,
            duration_minutes INTEGER NOT NULL,
            calories_burned REAL NOT NULL,
            entry_date DATE DEFAULT CURRENT_DATE,
            entry_time TIME DEFAULT CURRENT_TIME,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    ''')

    # Tabela para Metas
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS goals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            goal_type TEXT NOT NULL,
            target_value REAL NOT NULL,
            start_date DATE DEFAULT CURRENT_DATE,
            end_date DATE,
            FOREIGN KEY (user_id) REFERENCES users(id),
            UNIQUE (user_id, goal_type)
        )
    ''')

    # Tabela para Lembretes
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS reminders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            reminder_text TEXT NOT NULL,
            reminder_time TEXT NOT NULL,
            is_active BOOLEAN DEFAULT 1,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    ''')

    # Tabela para dados da TACO
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS taco_foods (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            alimento TEXT UNIQUE NOT NULL,
            energia_kcal REAL,
            proteina_g REAL,
            lipidios_g REAL,
            carboidrato_g REAL
        )
    ''')

    # NOVO: Tabela para gerenciar o estado da conversa do usuário
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS user_state (
            user_id INTEGER PRIMARY KEY, -- user_id é a chave primária e referência a users.id
            state TEXT NOT NULL,         -- O estado atual da conversa (ex: 'awaiting_meal_delete_number')
            context_data TEXT,           -- Dados JSON para contexto (ex: lista de IDs de refeição)
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    ''')

    conn.commit()
    conn.close()

def get_or_create_user(whatsapp_number):
    conn = sqlite3.connect(DATABASE_FILE)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM users WHERE whatsapp_number = ?", (whatsapp_number,))
    user = cursor.fetchone()
    if user:
        conn.close()
        return user['id']
    else:
        cursor.execute("INSERT INTO users (whatsapp_number) VALUES (?)", (whatsapp_number,))
        conn.commit()
        user_id = cursor.lastrowid
        conn.close()
        return user_id

def update_last_interaction_date(whatsapp_number):
    user_id = get_or_create_user(whatsapp_number)
    conn = get_db_connection()
    cursor = conn.cursor()
    today_date_str = date.today().strftime('%Y-%m-%d')
    cursor.execute(
        "UPDATE users SET last_interaction_date = ? WHERE id = ?",
        (today_date_str, user_id)
    )
    conn.commit()
    conn.close()

def get_last_interaction_date(whatsapp_number):
    user_id = get_or_create_user(whatsapp_number)
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT last_interaction_date FROM users WHERE id = ?",
        (user_id,)
    )
    result = cursor.fetchone()
    conn.close()
    if result and result['last_interaction_date']:
        return datetime.strptime(result['last_interaction_date'], '%Y-%m-%d').date()
    return None

def get_all_users():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT whatsapp_number FROM users")
    users = [row['whatsapp_number'] for row in cursor.fetchall()]
    conn.close()
    return users

def add_food_entry(whatsapp_number, foods_description, calories, carbohydrates, proteins, fats):
    user_id = get_or_create_user(whatsapp_number)
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO food_entries (user_id, foods_description, calories, carbohydrates, proteins, fats) VALUES (?, ?, ?, ?, ?, ?)",
        (user_id, foods_description, calories, carbohydrates, proteins, fats)
    )
    conn.commit()
    conn.close()

def add_weight_entry(whatsapp_number, weight):
    user_id = get_or_create_user(whatsapp_number)
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO weight_entries (user_id, weight) VALUES (?, ?)",
        (user_id, weight)
    )
    conn.commit()
    conn.close()

def add_exercise_entry(whatsapp_number, activity_name, duration_minutes, calories_burned):
    user_id = get_or_create_user(whatsapp_number)
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO exercise_entries (user_id, activity_name, duration_minutes, calories_burned) VALUES (?, ?, ?, ?)",
        (user_id, activity_name, duration_minutes, calories_burned)
    )
    conn.commit()
    conn.close()

def get_daily_summary(whatsapp_number):
    user_id = get_or_create_user(whatsapp_number)
    conn = get_db_connection()
    cursor = conn.cursor()
    today_date = date.today().strftime('%Y-%m-%d')

    summary = {
        'foods': [],
        'exercises': [],
        'last_weight': None
    }

    cursor.execute(
        "SELECT foods_description, calories, carbohydrates, proteins, fats FROM food_entries WHERE user_id = ? AND entry_date = ?",
        (user_id, today_date)
    )
    summary['foods'] = cursor.fetchall()

    cursor.execute(
        "SELECT activity_name, duration_minutes, calories_burned FROM exercise_entries WHERE user_id = ? AND entry_date = ?",
        (user_id, today_date)
    )
    summary['exercises'] = cursor.fetchall()

    cursor.execute(
        "SELECT weight FROM weight_entries WHERE user_id = ? ORDER BY entry_date DESC, entry_time DESC LIMIT 1",
        (user_id,)
    )
    last_weight_row = cursor.fetchone()
    if last_weight_row:
        summary['last_weight'] = last_weight_row['weight']

    conn.close()
    return summary

def set_goal(whatsapp_number, goal_type, target_value):
    user_id = get_or_create_user(whatsapp_number)
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute(
        "INSERT OR REPLACE INTO goals (user_id, goal_type, target_value) VALUES (?, ?, ?)",
        (user_id, goal_type, target_value)
    )
    conn.commit()
    conn.close()

def get_goal(whatsapp_number, goal_type):
    user_id = get_or_create_user(whatsapp_number)
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT target_value, start_date, end_date FROM goals WHERE user_id = ? AND goal_type = ?",
        (user_id, goal_type)
    )
    goal = cursor.fetchone()
    conn.close()
    return goal

def add_reminder(whatsapp_number, reminder_text, reminder_time_str):
    user_id = get_or_create_user(whatsapp_number)
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        datetime.strptime(reminder_time_str, '%H:%M').time()
    except ValueError:
        return False

    cursor.execute(
        "INSERT INTO reminders (user_id, reminder_text, reminder_time) VALUES (?, ?, ?)",
        (user_id, reminder_text, reminder_time_str)
    )
    conn.commit()
    conn.close()
    return True

def get_active_reminders():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT r.reminder_text, r.reminder_time, u.whatsapp_number "
        "FROM reminders r JOIN users u ON r.user_id = u.id "
        "WHERE r.is_active = 1"
    )
    reminders = cursor.fetchall()
    conn.close()
    return reminders

def get_user_reminders(whatsapp_number):
    user_id = get_or_create_user(whatsapp_number)
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT reminder_text, reminder_time FROM reminders WHERE user_id = ? AND is_active = 1",
        (user_id,)
    )
    reminders = cursor.fetchall()
    conn.close()
    return reminders

def deactivate_reminder(whatsapp_number, reminder_text, reminder_time_str):
    user_id = get_or_create_user(whatsapp_number)
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE reminders SET is_active = 0 WHERE user_id = ? AND reminder_text = ? AND reminder_time = ?",
        (user_id, reminder_text, reminder_time_str)
    )
    conn.commit()
    rows_affected = cursor.rowcount
    conn.close()
    return rows_affected > 0

# --- NOVAS FUNÇÕES PARA EXCLUSÃO DE REFEIÇÕES (EXISTENTES) ---

def delete_all_food_entries_for_day(whatsapp_number):
    """Deleta todas as entradas de comida para um usuário no dia atual."""
    user_id = get_or_create_user(whatsapp_number)
    conn = get_db_connection()
    cursor = conn.cursor()
    today_date_str = date.today().strftime('%Y-%m-%d')
    cursor.execute(
        "DELETE FROM food_entries WHERE user_id = ? AND entry_date = ?",
        (user_id, today_date_str)
    )
    conn.commit()
    rows_deleted = cursor.rowcount
    conn.close()
    return rows_deleted

def get_food_entries_for_day_indexed(whatsapp_number):
    """
    Retorna as entradas de comida do dia para um usuário, com seus IDs de DB,
    para que possam ser referenciadas por um índice (1, 2, 3...).
    """
    user_id = get_or_create_user(whatsapp_number)
    conn = get_db_connection()
    cursor = conn.cursor()
    today_date_str = date.today().strftime('%Y-%m-%d')
    # Ordena por ID para garantir consistência no índice
    cursor.execute(
        "SELECT id, foods_description, calories FROM food_entries WHERE user_id = ? AND entry_date = ? ORDER BY id ASC",
        (user_id, today_date_str)
    )
    entries = cursor.fetchall()
    conn.close()
    return entries

def delete_food_entry_by_id(entry_id):
    """Deleta uma entrada de comida específica pelo seu ID do banco de dados."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM food_entries WHERE id = ?", (entry_id,))
    conn.commit()
    rows_deleted = cursor.rowcount
    conn.close()
    return rows_deleted

# --- NOVAS FUNÇÕES PARA GERENCIAMENTO DE ESTADO ---
import json # Para armazenar context_data como JSON

def set_user_state(whatsapp_number, state, context_data=None):
    """Define o estado da conversa e dados de contexto para um usuário."""
    user_id = get_or_create_user(whatsapp_number)
    conn = get_db_connection()
    cursor = conn.cursor()
    
    context_json = json.dumps(context_data) if context_data else None

    # INSERT OR REPLACE atualiza se o user_id já existir, senão insere
    cursor.execute(
        "INSERT OR REPLACE INTO user_state (user_id, state, context_data) VALUES (?, ?, ?)",
        (user_id, state, context_json)
    )
    conn.commit()
    conn.close()
    print(f"DEBUG DB: Estado para {whatsapp_number} setado para '{state}' com contexto: {context_data}")

def get_user_state(whatsapp_number):
    """Retorna o estado da conversa e dados de contexto para um usuário."""
    user_id = get_or_create_user(whatsapp_number)
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT state, context_data FROM user_state WHERE user_id = ?",
        (user_id,)
    )
    result = cursor.fetchone()
    conn.close()
    
    if result:
        context_data = json.loads(result['context_data']) if result['context_data'] else {}
        print(f"DEBUG DB: Estado para {whatsapp_number} obtido: '{result['state']}' com contexto: {context_data}")
        return {'state': result['state'], 'context_data': context_data}
    print(f"DEBUG DB: Nenhum estado encontrado para {whatsapp_number}.")
    return {'state': 'none', 'context_data': {}} # Estado padrão