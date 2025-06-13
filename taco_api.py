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
    # Ex: "100g de arroz", "2 xicaras de cafe", "300 ml leite"
    match_quantity = re.search(r'(\d+)\s*(g|gramas|ml|litro|xicara|copo)?\s*(de|do|da|doce|roxa|crua)?\s*(.+)', query, re.IGNORECASE)
    
    if match_quantity:
        value = float(match_quantity.group(1))
        unit = match_quantity.group(2).lower() if match_quantity.group(2) else 'g' # Assume 'g' se unidade não especificada
        # O último grupo é o nome do alimento. Ignora "de", "do", "da", etc.
        alimento_base = match_quantity.group(4).strip() 

        # Converte para gramas ou ml (para usar na proporção de 100g)
        if unit in ['g', 'gramas']:
            quantidade_g = value
        elif unit in ['ml', 'litro']: 
            if unit == 'litro': quantidade_g = value * 1000
            else: quantidade_g = value
        elif unit in ['xicara', 'copo']:
            if unit == 'xicara': quantidade_g = value * 180 
            else: quantidade_g = value * 200 
        else:
            quantidade_g = 100.0 # Unidade desconhecida, assume 100g.
    else:
        alimento_base = query.strip() # Se não achou quantidade, a query é o alimento

    if not alimento_base:
        conn.close()
        return None

    # --- NOVA ESTRATÉGIA DE BUSCA NA TACO ---
    # 1. Tentar busca exata primeiro
    # 2. Tentar busca com LIKE para variações
    # 3. Tentar busca com palavras-chave separadas

    found_food = None

    # Normaliza o alimento base para busca
    alimento_base_normalized = alimento_base.lower().replace(" ", "%") # Ex: "arroz integral" -> "arroz%integral"

    search_queries = [
        alimento_base.replace(",", "").strip(), # Ex: "Arroz integral cozido"
        alimento_base.strip(), # Ex: "Arroz, integral, cozido" (com vírgulas)
        f"%{alimento_base.strip()}%", # "arroz" encontra "Arroz, integral, cozido"
        f"%{alimento_base_normalized}%" # "arroz%integral"
    ]
    
    # Adicionar termos mais genéricos se a consulta for muito específica
    # Ex: "contrafile" -> "carne"
    # Ex: "batata, cozida" -> "batata"
    generic_alimento_base = alimento_base.split(',')[0].strip() # Pega apenas a primeira parte
    if generic_alimento_base.lower() != alimento_base.lower():
        search_queries.append(generic_alimento_base)
        search_queries.append(f"%{generic_alimento_base}%")
        
    # Adicionar variações com e sem acento para busca
    alimento_sem_acento = (
        alimento_base.lower()
        .replace('á', 'a').replace('ã', 'a').replace('â', 'a')
        .replace('é', 'e').replace('ê', 'e')
        .replace('í', 'i')
        .replace('ó', 'o').replace('õ', 'o')
        .replace('ú', 'u')
        .replace('ç', 'c')
    )
    if alimento_sem_acento != alimento_base.lower():
        search_queries.append(alimento_sem_acento)
        search_queries.append(f"%{alimento_sem_acento}%")

    # Remove duplicatas e garante que a busca mais específica venha primeiro
    final_search_terms = []
    seen_terms = set()
    for term in search_queries:
        if term.lower() not in seen_terms:
            final_search_terms.append(term)
            seen_terms.add(term.lower())
    
    # Ordem de busca: exato > com % > genérico. Prioriza exato primeiro.
    final_search_terms.sort(key=lambda x: (x.count('%'), -len(x))) # Ordena para que exatos ou menos curingas venham antes

    for term in final_search_terms:
        # Usar COLLATE NOCASE para busca sem sensibilidade a maiusculas/minusculas
        cursor.execute("SELECT * FROM taco_foods WHERE alimento LIKE ? COLLATE NOCASE LIMIT 1", (term,)) 
        found_food = cursor.fetchone()
        if found_food:
            print(f"DEBUG TACO: Encontrado '{found_food['alimento']}' para busca '{term}'.") # Log de depuração
            break

    if found_food:
        # Calcula as proporções baseadas em 100g
        proportion = quantidade_g / 100.0

        calories = found_food['energia_kcal'] * proportion
        proteins = found_food['proteina_g'] * proportion
        fats = found_food['lipidios_g'] * proportion
        carbohydrates = found_food['carboidrato_g'] * proportion

        # Descrição para o usuário e DB (pega do DB para consistência)
        # Ex: "100g de Arroz, integral, cozido"
        food_description_for_output = f"{quantidade_g:.0f}g de {found_food['alimento']}" \
                                      if quantidade_g != 100.0 else found_food['alimento']


        conn.close()
        return {
            'calories': calories,
            'carbohydrates': carbohydrates,
            'proteins': proteins,
            'fats': fats,
            'foods_listed': food_description_for_output,
            'original_alimento': found_food['alimento'] # Nome original do TACO
        }
    else:
        conn.close()
        return None

# Teste (opcional)
if __name__ == '__main__':
    # Certifique-se que você já rodou import_taco_data.py para popular o DB
    print("--- Testando Taco API Localmente ---")
    
    # Testes com diferentes formatos
    info_batata = get_taco_nutrition("100g de batata")
    if info_batata:
        print(f"Batata: Cal: {info_batata['calories']:.0f}, Carb: {info_batata['carbohydrates']:.0f}, Prot: {info_batata['proteins']:.0f}, Gord: {info_batata['fats']:.0f}, Desc: {info_batata['foods_listed']}")
    else:
        print("Batata: Não encontrado.")

    info_arroz_cozido = get_taco_nutrition("Arroz, integral, cozido")
    if info_arroz_cozido:
        print(f"Arroz (puro): Cal: {info_arroz_cozido['calories']:.0f}, Carb: {info_arroz_cozido['carbohydrates']:.0f}, Prot: {info_arroz_cozido['proteins']:.0f}, Gord: {info_arroz_cozido['fats']:.0f}, Desc: {info_arroz_cozido['foods_listed']}")
    else:
        print("Arroz (puro): Não encontrado.")

    info_contrafile = get_taco_nutrition("contrafile") # contrafile nao esta na taco
    if info_contrafile:
        print(f"Contrafilé: Cal: {info_contrafile['calories']:.0f}, Carb: {info_contrafile['carbohydrates']:.0f}, Prot: {info_contrafile['proteins']:.0f}, Gord: {info_contrafile['fats']:.0f}, Desc: {info_contrafile['foods_listed']}")
    else:
        print("Contrafilé: Não encontrado na TACO.")
        
    info_arroz_200g = get_taco_nutrition("200g de arroz, integral, cozido")
    if info_arroz_200g:
        print(f"200g Arroz: Cal: {info_arroz_200g['calories']:.0f}, Carb: {info_arroz_200g['carbohydrates']:.0f}, Prot: {info_arroz_200g['proteins']:.0f}, Gord: {info_arroz_200g['fats']:.0f}, Desc: {info_arroz_200g['foods_listed']}")
    else:
        print("200g Arroz: Não encontrado.")

    info_feijao = get_taco_nutrition("100g de feijao preto cozido")
    if info_feijao:
        print(f"Feijão: Cal: {info_feijao['calories']:.0f}, Carb: {info_feijao['carbohydrates']:.0f}, Prot: {info_feijao['proteins']:.0f}, Gord: {info_feijao['fats']:.0f}, Desc: {info_feijao['foods_listed']}")
    else:
        print("Feijão: Não encontrado.")

    info_frango = get_taco_nutrition("frango")
    if info_frango:
        print(f"Frango: Cal: {info_frango['calories']:.0f}, Carb: {info_frango['carbohydrates']:.0f}, Prot: {info_frango['proteins']:.0f}, Gord: {info_frango['fats']:.0f}, Desc: {info_frango['foods_listed']}")
    else:
        print("Frango: Não encontrado.")