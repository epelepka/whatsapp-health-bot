
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

    alimento_base = query.strip() # Começa com a query inteira como base
    quantidade_g = 100.0

    # Tenta extrair a quantidade e o nome do alimento de forma mais robusta
    # Padrão: (número) (unidade) de (nome do alimento)
    match_quantity = re.search(r'(\d+)\s*(g|gramas|gr|ml|l)?\s*(?:de\s)?(.+)', query, re.IGNORECASE)
    
    if match_quantity:
        value = float(match_quantity.group(1))
        unit_raw = match_quantity.group(2)
        unit = unit_raw.lower() if unit_raw else 'g'
        alimento_base = match_quantity.group(3).strip() # O que vem depois de "de"

        if unit in ['g', 'gramas', 'gr']:
            quantidade_g = value
        elif unit in ['ml', 'l']:
            quantidade_g = value * 1000 if unit == 'l' else value
        # Adicionar outras conversões se necessário
    
    if not alimento_base:
        cursor.close()
        conn.close()
        return None

    found_food = None

    # --- LÓGICA DE BUSCA SIMPLIFICADA E CORRIGIDA ---
    # O termo de busca principal será o nome base do alimento
    # A consulta SQL já usará o operador ILIKE com %
    
    # Termo de busca mais importante:
    search_term = f'%{alimento_base}%'
    
    print(f"DEBUG: Tentando busca principal com o padrão: '{search_term}'")

    try:
        # A consulta agora usa o padrão com '%'
        cursor.execute("SELECT * FROM taco_foods WHERE alimento ILIKE %s ORDER BY LENGTH(alimento) LIMIT 1", (search_term,))
        row = cursor.fetchone()
        
        print(f"DEBUG: Resultado do DB para busca principal: {row}")

        if row:
            desc = cursor.description
            found_food = {col[0]: row[idx] for idx, col in enumerate(desc)}
            print(f"DEBUG TACO: Encontrado '{found_food['alimento']}' para busca '{alimento_base}'.")

    except Exception as e:
        print(f"ERRO durante a consulta: {e}")


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
        print(f"DEBUG: Nenhuma correspondência encontrada no DB para '{alimento_base}'.")
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