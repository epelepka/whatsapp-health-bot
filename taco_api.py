
from database import get_db_connection
import psycopg2
from psycopg2 import sql
import os
import re

def get_taco_nutrition(query):
    """
    Busca informações nutricionais de um alimento na tabela TACO (PostgreSQL).
    Retorna um dicionário com calorias, macros e a descrição do alimento, ou None.
    """
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

    # --- ESTE É O LOCAL CORRETO PARA A CONSULTA E O DEBUG ---
    for term in final_search_terms:
        try:
            cursor.execute("SELECT * FROM taco_foods WHERE alimento ILIKE %s LIMIT 1", (term,))
            row = cursor.fetchone()
            
            # NOSSO PRINT DE DEPURAÇÃO, NO LUGAR CERTO:
            print(f"DEBUG: Buscando por '{term}', Resultado do DB: {row}")

            if row:
                desc = cursor.description
                found_food = {col[0]: row[idx] for idx, col in enumerate(desc)}
                print(f"DEBUG TACO: Encontrado '{found_food['alimento']}' para busca '{term}'.")
                break # Sai do loop assim que encontrar o primeiro resultado
        except Exception as e:
            print(f"ERRO durante a consulta com o termo '{term}': {e}")


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