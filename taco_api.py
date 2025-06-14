# taco_api.py
import psycopg2
import re
import os

# Importa a função de conexão do outro arquivo
from database import get_db_connection

def search_taco_options(query):
    """
    Busca até 5 opções de alimentos na tabela TACO (PostgreSQL).
    Retorna uma LISTA de dicionários, cada um contendo os dados de um alimento.
    """
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        alimento_base = query.strip()
        quantidade_g = 100.0

        # Tenta extrair a quantidade e o nome do alimento de forma mais robusta
        # Padrão: (número) (unidade) de (nome do alimento)
        match_quantity = re.search(r'(\d+)\s*(g|gramas|gr|ml|l)?\s*(?:de\s)?(.+)', query, re.IGNORECASE)
        
        if match_quantity:
            value = float(match_quantity.group(1))
            unit_raw = match_quantity.group(2)
            unit = unit_raw.lower() if unit_raw else 'g'
            alimento_base = match_quantity.group(3).strip()

            if unit in ['g', 'gramas', 'gr']:
                quantidade_g = value
            elif unit in ['ml', 'l']:
                quantidade_g = value * 1000 if unit == 'l' else value
            # Adicionar outras conversões se necessário
        
        if not alimento_base:
            return [] # Retorna uma lista vazia se não houver nome de alimento

        found_options = []
        # O termo de busca usa '%' para buscas parciais (contém)
        search_term = f'%{alimento_base}%'
        
        # AQUI A MUDANÇA PRINCIPAL: Buscamos até 5 opções, ordenando pela mais curta
        cursor.execute("SELECT * FROM taco_foods WHERE alimento ILIKE %s ORDER BY LENGTH(alimento) LIMIT 5", (search_term,))
        rows = cursor.fetchall() # Usamos fetchall() para pegar todas as linhas
        
        print(f"DEBUG: Busca por '{search_term}' encontrou {len(rows)} resultados no DB.")

        desc = cursor.description
        for row in rows:
            # Converte a linha do banco de dados em um dicionário de fácil uso
            found_food = {col[0]: row[idx] for idx, col in enumerate(desc)}
            
            # Calcula a proporção baseada na quantidade informada (padrão é 100g)
            proportion = quantidade_g / 100.0
            
            # Monta o dicionário de dados para esta opção
            option_data = {
                'calories': found_food.get('energia_kcal', 0) * proportion,
                'carbohydrates': found_food.get('carboidrato_g', 0) * proportion,
                'proteins': found_food.get('proteina_g', 0) * proportion,
                'fats': found_food.get('lipidios_g', 0) * proportion,
                'foods_listed': f"{quantidade_g:.0f}g de {found_food['alimento']}" if quantidade_g != 100.0 else found_food['alimento'],
                'original_alimento': found_food['alimento']
            }
            found_options.append(option_data)

        return found_options

    except Exception as e:
        print(f"ERRO CRÍTICO em search_taco_options: {e}")
        return [] # Retorna lista vazia em caso de erro

    finally:
        if conn:
            cursor.close()
            conn.close()

