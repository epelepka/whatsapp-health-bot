import requests
import os
from dotenv import load_dotenv

load_dotenv()

WIT_AI_SERVER_ACCESS_TOKEN = os.getenv('WIT_AI_SERVER_ACCESS_TOKEN')
WIT_AI_API_URL = "[https://api.wit.ai/message](https://api.wit.ai/message)"

def get_wit_ai_response(text_message):
    headers = {
        "Authorization": f"Bearer {WIT_AI_SERVER_ACCESS_TOKEN}",
        "Content-Type": "application/json"
    }
    params = {
        "q": text_message,
        "v": "20240501" # Versão da API (use a data atual ou uma estável)
    }

    try:
        response = requests.get(WIT_AI_API_URL, headers=headers, params=params)
        response.raise_for_status() # Lança erro para status HTTP 4xx/5xx
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"Erro ao conectar com Wit.ai: {e}")
        return None
    except Exception as e:
        print(f"Erro inesperado ao processar resposta do Wit.ai: {e}")
        return None

def parse_wit_ai_response(wit_response):
    if not wit_response or 'intents' not in wit_response or not wit_response['intents']:
        return {'intent': 'none', 'entities': {}}

    # Pega a intenção com maior confiança
    main_intent = wit_response['intents'][0]['name']
    
    # Extrai as entidades
    entities = {}
    if 'entities' in wit_response:
        for entity_name, entity_list in wit_response['entities'].items():
            # A forma como você extrai depende de como você configurou a entidade no Wit.ai
            # e do que espera. wit/datetime é um caso especial.
            if entity_name == 'wit$datetime:datetime': # Exemplo de entidade built-in
                if entity_list and 'value' in entity_list[0]:
                    entities['datetime'] = entity_list[0]['value']
                    # Você pode precisar de lógica para pegar o fuso horário ou a hora específica
                    # dependendo da sua necessidade
                    if 'values' in entity_list[0] and entity_list[0]['values']:
                        for val in entity_list[0]['values']:
                            if 'type' in val and val['type'] == 'value' and 'value' in val:
                                entities['wit_time'] = val['value'] # Hora detectada pelo wit.ai
                                break
            elif entity_list and 'value' in entity_list[0]:
                entities[entity_name.replace(":", "_")] = entity_list[0]['value']
                # Se for uma entidade que pode ter múltiplos valores (ex: food_item)
                # você pode ajustar para pegar todos os values em uma lista
                # entities[entity_name.replace(":", "_")] = [e['value'] for e in entity_list]
    
    return {'intent': main_intent, 'entities': entities}

# Exemplo de uso (para testar)
if __name__ == '__main__':
    # Certifique-se que WIT_AI_SERVER_ACCESS_TOKEN está no seu .env
    test_phrases = [
        "Oi bot",
        "Comi um prato de arroz e feijao",
        "Meu peso e 70.5",
        "Eu corri por 45 minutos",
        "Me da o resumo do dia",
        "Define meta de calorias 1800",
        "Quero um lembrete para beber agua as 15:30"
    ]

    for phrase in test_phrases:
        print(f"\nFrase: '{phrase}'")
        wit_resp = get_wit_ai_response(phrase)
        parsed_data = parse_wit_ai_response(wit_resp)
        print(f"Intenção: {parsed_data['intent']}")
        print(f"Entidades: {parsed_data['entities']}")