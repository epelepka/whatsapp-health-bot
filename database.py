# database.py (Versão para PostgreSQL)
import os
import psycopg2 # Novo import para PostgreSQL
from psycopg2 import sql # Para construir queries seguras
from datetime import datetime, date, time
import json # Para user_state context_data

# URL de conexão com o PostgreSQL (será injetada pelo Railway como DATABASE_URL)
# Em desenvolvimento local, você pode definir DATABASE_URL no seu .env
DATABASE_URL = os.getenv('DATABASE_URL')

def get_db_connection():
    """Retorna uma conexão com o banco de dados PostgreSQL."""
    if not DATABASE_URL:
        raise ValueError("DATABASE_URL não está configurada! Não é possível conectar ao PostgreSQL.")

    # O psycopg2 precisa do SSLMode 'require' ou 'no-verify' para conexões externas
    # Railway geralmente pede require
    return psycopg2.connect(DATABASE_URL + "?sslmode=require") # Adicionado sslmode=require

def init_db():
    """Inicializa o esquema do banco de dados (cria tabelas se não existirem)."""
    conn = get_db_connection()
    cursor = conn.cursor()

    # Tabela de usuários
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY, -- SERIAL para autoincremento no PostgreSQL
            whatsapp_number TEXT UNIQUE NOT NULL,
            last_interaction_date DATE DEFAULT CURRENT_DATE
        );
    ''')

    # Tabela food_entries
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS food_entries (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id),
            foods_description TEXT NOT NULL,
            calories REAL NOT NULL,
            carbohydrates REAL DEFAULT 0,
            proteins REAL DEFAULT 0,
            fats REAL DEFAULT 0,
            entry_date DATE DEFAULT CURRENT_DATE,
            entry_time TIME DEFAULT CURRENT_TIME
        );
    ''')

    # Tabela weight_entries
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS weight_entries (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id),
            weight REAL NOT NULL,
            entry_date DATE DEFAULT CURRENT_DATE,
            entry_time TIME DEFAULT CURRENT_TIME
        );
    ''')

    # Tabela exercise_entries
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS exercise_entries (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id),
            activity_name TEXT NOT NULL,
            duration_minutes INTEGER NOT NULL,
            calories_burned REAL NOT NULL,
            entry_date DATE DEFAULT CURRENT_DATE,
            entry_time TIME DEFAULT CURRENT_TIME
        );
    ''')

    # Tabela goals
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS goals (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id),
            goal_type TEXT NOT NULL,
            target_value REAL NOT NULL,
            start_date DATE DEFAULT CURRENT_DATE,
            end_date DATE,
            UNIQUE (user_id, goal_type)
        );
    ''')

    # Tabela reminders
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS reminders (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id),
            reminder_text TEXT NOT NULL,
            reminder_time TEXT NOT NULL,
            is_active BOOLEAN DEFAULT TRUE 
        );
    ''')

    # Tabela taco_foods (Adaptada para PostgreSQL)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS taco_foods (
            id SERIAL PRIMARY KEY,
            alimento TEXT UNIQUE NOT NULL,
            energia_kcal REAL,
            proteina_g REAL,
            lipidios_g REAL,
            carboidrato_g REAL
        );
    ''')

    # Tabela user_state
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS user_state (
            user_id INTEGER PRIMARY KEY REFERENCES users(id),
            state TEXT NOT NULL,
            context_data TEXT -- JSON no PostgreSQL é TEXT ou JSONB
        );
    ''')

    conn.commit()
    cursor.close()
    conn.close()

# --- Funções de CRUD (adaptadas para PostgreSQL) ---
def _fetch_one_as_dict(cursor):
    row = cursor.fetchone()
    if row:
        desc = cursor.description
        return {col[0]: row[idx] for idx, col in enumerate(desc)}
    return None

def _fetch_all_as_dict(cursor):
    rows = cursor.fetchall()
    if not rows:
        return []
    desc = cursor.description
    return [{col[0]: row[idx] for idx, col in enumerate(desc)} for row in rows]


def get_or_create_user(whatsapp_number):
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT id FROM users WHERE whatsapp_number = %s", (whatsapp_number,))
    user = _fetch_one_as_dict(cursor)

    if user:
        cursor.close()
        conn.close()
        return user['id']
    else:
        cursor.execute("INSERT INTO users (whatsapp_number) VALUES (%s) RETURNING id", (whatsapp_number,))
        user_id = cursor.fetchone()[0]
        conn.commit()
        cursor.close()
        conn.close()
        return user_id

def update_last_interaction_date(whatsapp_number):
    user_id = get_or_create_user(whatsapp_number)
    conn = get_db_connection()
    cursor = conn.cursor()
    today_date_str = date.today().strftime('%Y-%m-%d')
    cursor.execute(
        "UPDATE users SET last_interaction_date = %s WHERE id = %s",
        (today_date_str, user_id)
    )
    conn.commit()
    cursor.close()
    conn.close()

def get_last_interaction_date(whatsapp_number):
    user_id = get_or_create_user(whatsapp_number)
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT last_interaction_date FROM users WHERE id = %s",
        (user_id,)
    )
    result = _fetch_one_as_dict(cursor)
    cursor.close()
    conn.close()
    if result and result['last_interaction_date']:
        return result['last_interaction_date'] 
    return None

def get_all_users():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT whatsapp_number FROM users")
    users = [row[0] for row in cursor.fetchall()]
    cursor.close()
    conn.close()
    return users

def add_food_entry(whatsapp_number, foods_description, calories, carbohydrates, proteins, fats):
    user_id = get_or_create_user(whatsapp_number)
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO food_entries (user_id, foods_description, calories, carbohydrates, proteins, fats, entry_date, entry_time) VALUES (%s, %s, %s, %s, %s, %s, CURRENT_DATE, CURRENT_TIME)",
        (user_id, foods_description, calories, carbohydrates, proteins, fats)
    )
    conn.commit()
    cursor.close()
    conn.close()

def add_weight_entry(whatsapp_number, weight):
    user_id = get_or_create_user(whatsapp_number)
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO weight_entries (user_id, weight, entry_date, entry_time) VALUES (%s, %s, CURRENT_DATE, CURRENT_TIME)",
        (user_id, weight)
    )
    conn.commit()
    cursor.close()
    conn.close()

def add_exercise_entry(whatsapp_number, activity_name, duration_minutes, calories_burned):
    user_id = get_or_create_user(whatsapp_number)
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO exercise_entries (user_id, activity_name, duration_minutes, calories_burned, entry_date, entry_time) VALUES (%s, %s, %s, %s, CURRENT_DATE, CURRENT_TIME)",
        (user_id, activity_name, duration_minutes, calories_burned)
    )
    conn.commit()
    cursor.close()
    conn.close()

def get_daily_summary(whatsapp_number):
    user_id = get_or_create_user(whatsapp_number)
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute(
        "SELECT foods_description, calories, carbohydrates, proteins, fats FROM food_entries WHERE user_id = %s AND entry_date = CURRENT_DATE",
        (user_id,)
    )
    summary_foods = _fetch_all_as_dict(cursor)

    cursor.execute(
        "SELECT activity_name, duration_minutes, calories_burned FROM exercise_entries WHERE user_id = %s AND entry_date = CURRENT_DATE",
        (user_id,)
    )
    summary_exercises = _fetch_all_as_dict(cursor)

    cursor.execute(
        "SELECT weight FROM weight_entries WHERE user_id = %s ORDER BY entry_date DESC, entry_time DESC LIMIT 1",
        (user_id,)
    )
    last_weight_row = _fetch_one_as_dict(cursor)

    cursor.close()
    conn.close()

    summary = {
        'foods': summary_foods,
        'exercises': summary_exercises,
        'last_weight': last_weight_row['weight'] if last_weight_row else None
    }
    return summary

def set_goal(whatsapp_number, goal_type, target_value):
    user_id = get_or_create_user(whatsapp_number)
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute(
        "INSERT INTO goals (user_id, goal_type, target_value, start_date) VALUES (%s, %s, %s, CURRENT_DATE) ON CONFLICT (user_id, goal_type) DO UPDATE SET target_value = EXCLUDED.target_value, start_date = EXCLUDED.start_date",
        (user_id, goal_type, target_value)
    )
    conn.commit()
    cursor.close()
    conn.close()

def get_goal(whatsapp_number, goal_type):
    user_id = get_or_create_user(whatsapp_number)
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT target_value, start_date, end_date FROM goals WHERE user_id = %s AND goal_type = %s",
        (user_id, goal_type)
    )
    goal = _fetch_one_as_dict(cursor)
    cursor.close()
    conn.close()
    return goal

def add_reminder(whatsapp_number, reminder_text, reminder_time_str):
    user_id = get_or_create_user(whatsapp_number)
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        time_obj = datetime.strptime(reminder_time_str, '%H:%M').time()
    except ValueError:
        return False

    cursor.execute(
        "INSERT INTO reminders (user_id, reminder_text, reminder_time, is_active) VALUES (%s, %s, %s, TRUE)",
        (user_id, reminder_text, reminder_time_str)
    )
    conn.commit()
    cursor.close()
    conn.close()
    return True

def get_active_reminders():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT r.reminder_text, r.reminder_time, u.whatsapp_number "
        "FROM reminders r JOIN users u ON r.user_id = u.id "
        "WHERE r.is_active = TRUE"
    )
    reminders = _fetch_all_as_dict(cursor)
    cursor.close()
    conn.close()
    return reminders

def get_user_reminders(whatsapp_number):
    user_id = get_or_create_user(whatsapp_number)
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT reminder_text, reminder_time FROM reminders WHERE user_id = %s AND is_active = TRUE",
        (user_id,)
    )
    reminders = _fetch_all_as_dict(cursor)
    cursor.close()
    conn.close()
    return reminders

def deactivate_reminder(whatsapp_number, reminder_text, reminder_time_str):
    user_id = get_or_create_user(whatsapp_number)
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE reminders SET is_active = FALSE WHERE user_id = %s AND reminder_text = %s AND reminder_time = %s",
        (user_id, reminder_text, reminder_time_str)
    )
    conn.commit()
    rows_affected = cursor.rowcount
    cursor.close()
    conn.close()
    return rows_affected > 0

def delete_all_food_entries_for_day(whatsapp_number):
    user_id = get_or_create_user(whatsapp_number)
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "DELETE FROM food_entries WHERE user_id = %s AND entry_date = CURRENT_DATE",
        (user_id,)
    )
    conn.commit()
    rows_deleted = cursor.rowcount
    cursor.close()
    conn.close()
    return rows_deleted

def get_food_entries_for_day_indexed(whatsapp_number):
    user_id = get_or_create_user(whatsapp_number)
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id, foods_description, calories FROM food_entries WHERE user_id = %s AND entry_date = CURRENT_DATE ORDER BY id ASC",
        (user_id,)
    )
    entries = _fetch_all_as_dict(cursor)
    cursor.close()
    conn.close()
    return entries

def delete_food_entry_by_id(entry_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM food_entries WHERE id = %s", (entry_id,))
    conn.commit()
    rows_deleted = cursor.rowcount
    cursor.close()
    conn.close()
    return rows_deleted