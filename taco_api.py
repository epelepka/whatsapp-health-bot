# taco_api.py
import sqlite3
import os
import re 

# Define o nome do arquivo do banco de dados (o mesmo que no database.py)
DATABASE_FILE = 'health_assistant.db'

def get_db_connection():
    """Retorna uma conexão com o banco de dados SQLite."""
    conn = sqlite3.connect(DATABASE_FILE)
    conn.row_factory = sqlite3.Row # Para acessar colunas por nome
    return conn

def get_taco_nutrition(query):
    """
    Busca informações nutricionais de um alimento na tabela TACO.
    A query pode ser um nome de alimento (ex: "arroz") ou "quantidade unidade de alimento" (ex: "100g de arroz").
    Retorna um dicionário com calorias, macros e a descrição do alimento, ou None.
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    alimento_base = None
    quantidade_g = 100.0 # Padrão para 100g se a quantidade não for especificada ou reconhecida

    # Tenta extrair quantidade e alimento da query (similar à Nutritionix)
    match_quantity = re.search(r'(\d+)\s*(g|gramas|ml|litro|xicara|copo)?\s*(de|do|da|doce|roxa|crua)?\s*(.+)', query, re.IGNORECASE)
    
    if match_quantity:
        value = float(match_quantity.group(1))
        unit = match_quantity.group(2).lower() if match_quantity.group(2) else 'g' # Assume 'g' se unidade não especificada
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
        conn.close()
        return None

    # --- NOVA ESTRATÉGIA DE BUSCA NA TACO (MAIS ROBUSTA) ---
    found_food = None

    # Função auxiliar para remover acentos e caracteres especiais
    def normalize_string(s):
        if not isinstance(s, str): return ""
        s = s.lower()
        s = re.sub(r'[áàãâä]', 'a', s)
        s = re.sub(r'[éèêë]', 'e', s)
        s = re.sub(r'[íìîï]', 'i', s)
        s = re.sub(r'[óòõôö]', 'o', s)
        s = re.sub(r'[úùûü]', 'u', s)
        s = re.sub(r'[ç]', 'c', s)
        s = re.sub(r'[^a-z0-9\s,]', '', s) # Remove caracteres não alfanuméricos exceto espaços e vírgulas
        return s

    alimento_base_normalized = normalize_string(alimento_base)
    
    # Tentativas de busca em ordem de prioridade
    search_queries = [
        alimento_base, # Busca exata (com acentos e pontuação original)
        alimento_base.replace(",", "").strip(), # Ex: "Arroz integral cozido"
        normalize_string(alimento_base).replace(",", "").strip(), # Ex: "arroz integral cozido" (sem acento/pontuação)
        f"%{alimento_base}%", # Contém o termo
        f"%{alimento_base.replace(' ', '%')}%", # Termo com múltiplos espaços
        f"%{alimento_base_normalized}%", # Termo normalizado (sem acento)
        f"%{alimento_base_normalized.replace(' ', '%')}%" # Termo normalizado com múltiplos espaços
    ]
    
    # Adiciona a busca pelo termo mais genérico se a consulta for composta (ex: "Feijão" para "Feijão, preto, cozido")
    generic_alimento_base = alimento_base.split(',')[0].strip()
    if generic_alimento_base.lower() != alimento_base.lower() and generic_alimento_base not in search_queries:
        search_queries.append(generic_alimento_base)
        search_queries.append(normalize_string(generic_alimento_base))
        search_queries.append(f"%{generic_alimento_base}%")
        search_queries.append(f"%{normalize_string(generic_alimento_base)}%")

    # Remove duplicatas e ordena para que as buscas mais específicas venham primeiro
    final_search_terms = []
    seen_terms = set()
    for term in search_queries:
        normalized_term_for_set = normalize_string(term) # Normaliza para o set
        if normalized_term_for_set not in seen_terms and term.strip(): # Garante que não está vazio
            final_search_terms.append(term.strip())
            seen_terms.add(normalized_term_for_set)
    
    # Ordena para priorizar nomes puros e menos curingas
    final_search_terms.sort(key=lambda x: (
        x.count('%'), # Menos % (mais exato) vem antes
        -len(x)       # Mais longo (mais específico) vem antes, se tiver o mesmo %
    ))

    for term in final_search_terms:
        # Usar COLLATE NOCASE para busca sem sensibilidade a maiusculas/minusculas
        cursor.execute("SELECT * FROM taco_foods WHERE alimento LIKE ? COLLATE NOCASE LIMIT 1", (term,)) 
        found_food = cursor.fetchone()
        if found_food:
            print(f"DEBUG TACO: Encontrado '{found_food['alimento']}' para busca '{term}'.") 
            break

    if found_food:
        # Calcula as proporções baseadas em 100g
        proportion = quantidade_g / 100.0

        calories = found_food['energia_kcal'] * proportion
        proteins = found_food['proteina_g'] * proportion
        fats = found_food['lipidios_g'] * proportion
        carbohydrates = found_food['carboidrato_g'] * proportion

        food_description_for_output = f"{quantidade_g:.0f}g de {found_food['alimento']}" \
                                      if quantidade_g != 100.0 else found_food['alimento']


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
        conn.close()
        return None

# Teste (opcional)
if __name__ == '__main__':
    # Certifique-se que você já rodou import_taco_data.py para popular o DB
    print("--- Testando Taco API Localmente ---")
    
    test_queries = [
        "arroz",
        "100g de arroz",
        "feijao",
        "50g de feijao",
        "batata",
        "100g de batata",
        "contrafile", # Geralmente não está na TACO com esse nome
        "frango grelhado", # Deve encontrar "Frango, filé, grelhado"
        "arroz integral cozido",
        "cafe"
    ]
    
    for query in test_queries:
        print(f"\nBuscando: '{query}'")
        info = get_taco_nutrition(query)
        if info:
            print(f"  Encontrado: {info['foods_listed']} | Cal: {info['calories']:.0f} | Carb: {info['carbohydrates']:.0f} | Prot: {info['proteins']:.0f} | Gord: {info['fats']:.0f}")
        else:
            print(f"  Não encontrado para '{query}'.")