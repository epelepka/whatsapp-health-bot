# taco_api.py
import sqlite3
import os
import re # Para processar nomes de alimentos

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
    match_quantity = re.search(r'(\d+)\s*(g|gramas|ml|litro|xicara|copo)\s*(de)?\s*(.+)', query, re.IGNORECASE)
    
    if match_quantity:
        value = float(match_quantity.group(1))
        unit = match_quantity.group(2).lower()
        alimento_base = match_quantity.group(4).strip()

        # Converte para gramas ou ml (para usar na proporção de 100g)
        if unit in ['g', 'gramas']:
            quantidade_g = value
        elif unit in ['ml', 'litro']: # Assumindo densidade de 1g/ml para líquidos para fins de cálculo
            if unit == 'litro': quantidade_g = value * 1000
            else: quantidade_g = value
        elif unit in ['xicara', 'copo']: # Conversões aproximadas, podem ser melhoradas
            if unit == 'xicara': quantidade_g = value * 180 # Aprox. 180g para uma xícara de arroz, varia muito
            else: quantidade_g = value * 200 # Aprox. 200g para um copo de água, varia muito
        else: # Unidade desconhecida, assume 100g e tenta o alimento base
            quantidade_g = 100.0 # Usa a quantidade padrão
    else:
        alimento_base = query.strip() # Se não achou quantidade, a query é o alimento

    if not alimento_base:
        conn.close()
        return None

    # Tenta buscar o alimento na tabela TACO
    # Usar LIKE para buscas parciais (ex: "arroz" encontra "Arroz, integral, cozido")
    # Tenta primeiro a busca exata ou a mais próxima
    search_terms = [
        alimento_base, # Busca exata
        f"%{alimento_base}%", # Busca contendo a palavra
        f"%{alimento_base.replace(' ', '%')}%" # Busca com espaços como curingas
    ]
    
    found_food = None
    for term in search_terms:
        cursor.execute("SELECT * FROM taco_foods WHERE alimento LIKE ? LIMIT 1", (term,))
        found_food = cursor.fetchone()
        if found_food:
            break

    if found_food:
        # Calcula as proporções baseadas em 100g
        proportion = quantidade_g / 100.0

        calories = found_food['energia_kcal'] * proportion
        proteins = found_food['proteina_g'] * proportion
        fats = found_food['lipidios_g'] * proportion
        carbohydrates = found_food['carboidrato_g'] * proportion

        # Descrição para o usuário e DB (pega do DB para consistência)
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