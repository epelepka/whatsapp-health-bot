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
    
    conn = psycopg2.connect(DATABASE_URL)
    # A psycopg2.extras.DictCursor (ou RealDictCursor) é como conn.row_factory=sqlite3.Row
    # mas precisa ser importada e usada com o cursor.
    # Por simplicidade, vamos pegar tuplas e mapear manualmente para dicionários se necessário
    return conn

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
            is_active BOOLEAN DEFAULT TRUE -- TRUE para booleanos no PostgreSQL
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
# Em PostgreSQL, para pegar o resultado como dicionário, pode usar DictCursor ou mapear manualmente.
# Para simplicidade e compatibilidade com o retorno de 'Row' do SQLite, faremos um mapeamento manual.

def _fetch_one_as_dict(cursor):
    """Helper para buscar uma linha como dicionário."""
    row = cursor.fetchone()
    if row:
        desc = cursor.description
        return {col[0]: row[idx] for idx, col in enumerate(desc)}
    return None

def _fetch_all_as_dict(cursor):
    """Helper para buscar todas as linhas como lista de dicionários."""
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
        cursor.execute("INSERT INTO users (whatsapp_number) VALUES (%s) RETURNING id", (whatsapp_number,)) # RETURNING id para pegar o ID gerado
        user_id = cursor.fetchone()[0] # Pega o ID retornado
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
        return result['last_interaction_date'] # PostgreSQL retorna como objeto date
    return None

def get_all_users():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT whatsapp_number FROM users")
    users = [row[0] for row in cursor.fetchall()] # Pega apenas a primeira coluna (whatsapp_number)
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
    today_date_str = date.today().strftime('%Y-%m-%d')

    summary = {
        'foods': [],
        'exercises': [],
        'last_weight': None
    }

    cursor.execute(
        "SELECT foods_description, calories, carbohydrates, proteins, fats FROM food_entries WHERE user_id = %s AND entry_date = CURRENT_DATE",
        (user_id,)
    )
    summary['foods'] = _fetch_all_as_dict(cursor)

    cursor.execute(
        "SELECT activity_name, duration_minutes, calories_burned FROM exercise_entries WHERE user_id = %s AND entry_date = CURRENT_DATE",
        (user_id,)
    )
    summary['exercises'] = _fetch_all_as_dict(cursor)

    cursor.execute(
        "SELECT weight FROM weight_entries WHERE user_id = %s ORDER BY entry_date DESC, entry_time DESC LIMIT 1",
        (user_id,)
    )
    last_weight_row = _fetch_one_as_dict(cursor)
    if last_weight_row:
        summary['last_weight'] = last_weight_row['weight']

    cursor.close()
    conn.close()
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
        # PostgreSQL precisa do formato correto para TIME
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
    # Junta reminders com users para pegar o whatsapp_number
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

# --- Funções para TACO (adaptadas para PostgreSQL) ---
# A função get_taco_nutrition buscará diretamente no PostgreSQL
def get_taco_nutrition(query):
    conn = get_db_connection()
    cursor = conn.cursor()

    alimento_base = None
    quantidade_g = 100.0

    match_quantity = re.search(r'(\d+)\s*(g|gramas|ml|litro|xicara|copo)?\s*(de|do|da|dos|das)?\s*(.+)', query, re.IGNORECASE)
    
    if match_quantity:
        value = float(match_quantity.group(1))
        unit = match_quantity.group(2).lower() if match_quantity.group(2) else 'g'
        alimento_base = match_quantity.group(4).strip() 

        if unit in ['g', 'gramas']:
            quantidade_g = value
        elif unit in ['ml', 'litro']:
            if unit == 'litro': quantidade_g = value * 1000
            else: quantidade_g = value
        elif unit in ['xicara', 'copo']:
            if unit == 'xicara': quantidade_g = value * 180 
            else: quantidade_g = value * 200 
        else:
            quantidade_g = 100.0 
    else:
        alimento_base = query.strip() 

    if not alimento_base:
        cursor.close()
        conn.close()
        return None

    found_food = None

    def normalize_string(s):
        if not isinstance(s, str): return ""
        s = s.lower()
        s = re.sub(r'[áàãâä]', 'a', s)
        s = re.sub(r'[éèêë]', 'e', s)
        s = re.sub(r'[íìîï]', 'i', s)
        s = re.sub(r'[óòõôö]', 'o', s)
        s = re.sub(r'[úùûü]', 'u', s)
        s = re.sub(r'[ç]', 'c', s)
        s = re.sub(r'[^a-z0-9\s,]', '', s)
        return s

    alimento_base_normalized = normalize_string(alimento_base)
    
    search_queries = [
        alimento_base.replace(",", "").strip(), 
        alimento_base.strip(), 
        normalize_string(alimento_base).replace(",", "").strip(), 
        f"%{alimento_base}%", 
        f"%{alimento_base.replace(' ', '%')}%", 
        f"%{alimento_base_normalized}%", 
        f"%{alimento_base_normalized.replace(' ', '%')}%" 
    ]
    
    generic_alimento_base = alimento_base.split(',')[0].strip()
    if generic_alimento_base.lower() != alimento_base.lower() and generic_alimento_base not in search_queries:
        search_queries.append(generic_alimento_base)
        search_queries.append(normalize_string(generic_alimento_base))
        search_queries.append(f"%{generic_alimento_base}%")
        search_queries.append(f"%{normalize_string(generic_alimento_base)}%")

    final_search_terms = []
    seen_terms = set()
    for term in search_queries:
        normalized_term_for_set = normalize_string(term)
        if normalized_term_for_set not in seen_terms and term.strip():
            final_search_terms.append(term.strip())
            seen_terms.add(normalized_term_for_set)
    
    final_search_terms.sort(key=lambda x: (
        x.count('%'), 
        -len(x)       
    ))

    for term in final_search_terms:
        # Para PostgreSQL, use ILIKE para busca case-insensitive e %s para parâmetros
        cursor.execute("SELECT * FROM taco_foods WHERE alimento ILIKE %s LIMIT 1", (term,)) 
        found_food = _fetch_one_as_dict(cursor)
        if found_food:
            print(f"DEBUG TACO: Encontrado '{found_food['alimento']}' para busca '{term}'.")
            break

    if found_food:
        proportion = quantidade_g / 100.0

        calories = found_food['energia_kcal'] * proportion
        proteins = found_food['proteina_g'] * proportion
        fats = found_food['lipidios_g'] * proportion
        carbohydrates = found_food['carboidrato_g'] * proportion

        food_description_for_output = f"{quantidade_g:.0f}g de {found_food['alimento']}" \
                                      if quantidade_g != 100.0 else found_food['alimento']


        cursor.close()
        conn.close()
        return {
            'calories': calories,
            'carbohydrates': carbohydrates,
            'proteins': proteins,
            'fats': fats,
            'foods_listed': food_description_for_output,
            'original_alimento': found_food['alimento'] 
        }
    else:
        cursor.close()
        conn.close()
        return None
