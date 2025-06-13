# nutrition_api.py
import requests
import os
from dotenv import load_dotenv

load_dotenv()

NUTRITIONIX_APP_ID = os.getenv('NUTRITIONIX_APP_ID')
NUTRITIONIX_APP_KEY = os.getenv('NUTRITIONIX_APP_KEY')
NUTRITIONIX_API_URL = "https://trackapi.nutritionix.com/v2/natural/nutrients"

def get_nutrition_info(query):
    headers = {
        "x-app-id": NUTRITIONIX_APP_ID,
        "x-app-key": NUTRITIONIX_APP_KEY,
        "Content-Type": "application/json"
    }
    payload = {
        "query": query
    }

    try:
        response = requests.post(NUTRITIONIX_API_URL, json=payload, headers=headers)
        response.raise_for_status() # Lança uma exceção para códigos de status HTTP de erro (4xx ou 5xx)
        data = response.json()

        total_calories = 0
        total_carbohydrates = 0 # NOVO
        total_proteins = 0      # NOVO
        total_fats = 0          # NOVO
        foods_listed = []

        if 'foods' in data:
            for food in data['foods']:
                food_name = food.get('food_name', 'Desconhecido')
                nf_calories = food.get('nf_calories', 0)
                nf_carbohydrates = food.get('nf_total_carbohydrate', 0) # NOVO
                nf_proteins = food.get('nf_protein', 0)               # NOVO
                nf_fats = food.get('nf_total_fat', 0)                 # NOVO
                
                total_calories += nf_calories
                total_carbohydrates += nf_carbohydrates # NOVO
                total_proteins += nf_proteins           # NOVO
                total_fats += nf_fats                   # NOVO

                # Para mostrar detalhadamente, pode adicionar macros aqui ou apenas o nome
                foods_listed.append(f"{food_name} ({nf_calories:.0f} kcal)")

            return {
                'calories': total_calories,
                'carbohydrates': total_carbohydrates, # NOVO
                'proteins': total_proteins,           # NOVO
                'fats': total_fats,                   # NOVO
                'foods_listed': ", ".join(foods_listed)
            }
        else:
            return None

    except requests.exceptions.RequestException as e:
        print(f"Erro ao conectar com a API Nutritionix: {e}")
        return None
    except Exception as e:
        print(f"Erro inesperado ao processar dados da Nutritionix: {e}")
        return None

# Teste (opcional)
if __name__ == '__main__':
    # Certifique-se que NUTRITIONIX_APP_ID e NUTRITIONIX_APP_KEY estão no seu .env
    print("--- Testando Nutritionix API com Macronutrientes ---")
    info = get_nutrition_info("1 maça, 200g arroz cozido, 100g peito de frango")
    if info:
        print(f"Calorias: {info['calories']:.2f}, Carb: {info['carbohydrates']:.2f}, Prot: {info['proteins']:.2f}, Gord: {info['fats']:.2f}, Alimentos: {info['foods_listed']}")
    else:
        print("Não foi possível obter informações nutricionais.")

        # nutrition_api.py (no final do arquivo)
# ... (restante do código das funções) ...

# Teste temporário para depuração
if __name__ == '__main__':
    # Certifique-se que NUTRITIONIX_APP_ID e NUTRITIONIX_APP_KEY estão no seu .env LOCAL
    # E QUE SÃO OS MESMOS QUE VOCÊ COLOCOU NO RAILWAY
    print("--- Testando Nutritionix API Localmente ---")

    # Use o mesmo formato de consulta que o seu app enviaria
    info = get_nutrition_info("100g de batata") # ou "100g batata" se preferir testar
    if info:
        print(f"Sucesso! Dados para '100g de batata':")
        print(f"Calorias: {info['calories']:.2f}, Carb: {info['carbohydrates']:.2f}, Prot: {info['proteins']:.2f}, Gord: {info['fats']:.2f}")
        print(f"Alimentos listados: {info['foods_listed']}")
    else:
        print("Falha! Não encontrou dados nutricionais para '100g de batata'. Verifique a API e as credenciais.")

    info_frango_arroz = get_nutrition_info("100g de contrafile e 100g de arroz")
    if info_frango_arroz:
        print(f"\nSucesso! Dados para '100g de contrafile e 100g de arroz':")
        print(f"Calorias: {info_frango_arroz['calories']:.2f}, Carb: {info_frango_arroz['carbohydrates']:.2f}, Prot: {info_frango_arroz['proteins']:.2f}, Gord: {info_frango_arroz['fats']:.2f}")
        print(f"Alimentos listados: {info_frango_arroz['foods_listed']}")