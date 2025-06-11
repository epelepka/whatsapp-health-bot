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
        foods_listed = []

        if 'foods' in data:
            for food in data['foods']:
                food_name = food.get('food_name', 'Desconhecido')
                nf_calories = food.get('nf_calories', 0)
                total_calories += nf_calories
                foods_listed.append(f"{food_name} ({nf_calories:.0f} kcal)")

            return {
                'calories': total_calories,
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
    # Estes valores precisam ser reais para o teste funcionar.
    # Exemplo (NÃO USE ESTES, use os seus do .env):
    # os.environ['NUTRITIONIX_APP_ID'] = 'SEU_APP_ID_AQUI'
    # os.environ['NUTRITIONIX_APP_KEY'] = 'SUA_CHAVE_AQUI'

    print("--- Testando Nutritionix API ---")
    info = get_nutrition_info("1 maça, 200g arroz cozido, 100g peito de frango")
    if info:
        print(f"Calorias: {info['calories']:.2f}, Alimentos: {info['foods_listed']}")
    else:
        print("Não foi possível obter informações nutricionais para '1 maça, 200g arroz cozido, 100g peito de frango'.")

    info = get_nutrition_info("pizza")
    if info:
        print(f"Calorias: {info['calories']:.2f}, Alimentos: {info['foods_listed']}")
    else:
        print("Não foi possível obter informações nutricionais para 'pizza'.")