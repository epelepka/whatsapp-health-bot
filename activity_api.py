# activity_api.py

# Valores MET aproximados para atividades comuns (ajuste conforme necessário)
# Fonte: Compendium of Physical Activities (Ainsworth et al., 2011)
MET_VALUES = {
    "corrida": 9.8,        # Correndo a ~8km/h
    "caminhada": 3.5,     # Caminhada rápida ~5km/h
    "musculacao": 3.0,    # Treino de força geral
    "natacao": 6.0,       # Nado moderado
    "ciclismo": 7.5,      # Ciclismo moderado
    "futebol": 7.0,
    "basquete": 6.0,
    "yoga": 2.5,
    "danca": 4.5,
    "aerobica": 5.0,
    "elíptico": 5.0,
    "remada": 4.8
}

def calculate_calories_burned(activity_name, duration_minutes, weight_kg):
    # Padroniza o nome da atividade para buscar no dicionário
    activity_name_normalized = activity_name.lower().replace(" ", "").strip()

    # Tenta encontrar uma correspondência exata ou aproximada
    met = 0
    for key, value in MET_VALUES.items():
        if key in activity_name_normalized or activity_name_normalized in key:
            met = value
            break
    
    if met == 0:
        print(f"MET não encontrado para atividade: {activity_name}")
        return 0 # Atividade não reconhecida ou MET não disponível

    # Fórmula para calorias queimadas
    # Calorias = (MET * peso em kg * duração em minutos * 3.5) / 200
    # O 3.5 é um fator de conversão de ml/kg/min de oxigênio para calorias
    calories = (met * weight_kg * duration_minutes) / 200 # A fórmula é com 3.5/1000 e dividida por 5, mas essa simplificação é comum

    return calories

# Teste (opcional)
if __name__ == '__main__':
    # Assumindo uma pessoa de 70kg
    print(f"Calorias queimadas (corrida 30 min, 70kg): {calculate_calories_burned('corrida', 30, 70):.2f}")
    print(f"Calorias queimadas (caminhada 60 min, 70kg): {calculate_calories_burned('caminhada', 60, 70):.2f}")
    print(f"Calorias queimadas (musculacao 45 min, 80kg): {calculate_calories_burned('musculacao', 45, 80):.2f}")
    print(f"Calorias queimadas (atividade desconhecida 30 min, 70kg): {calculate_calories_burned('pintar parede', 30, 70):.2f}")