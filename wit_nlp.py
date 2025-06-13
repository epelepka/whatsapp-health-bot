# wit_nlp.py

import requests
import os
from dotenv import load_dotenv
import re # Adicionado para uso na função de parse
from datetime import datetime # Adicionado para uso na função de parse

load_dotenv()

WIT_AI_SERVER_ACCESS_TOKEN = os.getenv('WIT_AI_SERVER_ACCESS_TOKEN')
WIT_AI_API_URL = "https://api.wit.ai/message"

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
        # Se nenhuma intenção for detectada ou a confiança for muito baixa,
        # o Wit.ai pode retornar uma lista de intenções vazia.
        # Consideramos 'none' se a confiança da primeira intenção for muito baixa (ex: < 0.7)
        # ou se a lista de intenções estiver vazia.
        if not wit_response['intents'] or wit_response['intents'][0]['confidence'] < 0.7:
             return {'intent': 'none', 'entities': {}}
        main_intent = wit_response['intents'][0]['name']
    else:
        main_intent = wit_response['intents'][0]['name'] # Pega a intenção com maior confiança
    
    entities = {}
    if 'entities' in wit_response:
        for entity_full_name, entity_list in wit_response['entities'].items():
            # Extrai apenas o nome principal da entidade (ex: 'food_item', 'quantity')
            entity_name_short = entity_full_name.split(':')[0] 

            if entity_name_short == 'wit$datetime': # Entidade de data/hora built-in
                if entity_list:
                    # wit/datetime pode retornar múltiplos valores (futuro/passado). Pegamos o primeiro.
                    # 'value' é a string ISO completa (ex: '2025-06-11T10:00:00.000-03:00')
                    # 'wit_time' será a string HH:MM ou a string ISO completa se não for possível formatar
                    wit_time_value = entity_list[0].get('value')
                    
                    if wit_time_value:
                        try:
                            # Tenta pegar a hora específica que o wit.ai pode ter retornado em 'values'
                            for val in entity_list[0].get('values', []):
                                if val.get('type') == 'value' and 'value' in val:
                                    # Se já for HH:MM, usa. Senão, tenta parsear como datetime.
                                    if re.match(r'^\d{2}:\d{2}$', val['value']):
                                        entities['wit_time'] = val['value'] 
                                    else:
                                        dt_object = datetime.fromisoformat(val['value'].replace('Z', '+00:00'))
                                        entities['wit_time'] = dt_object.strftime('%H:%M')
                                    break # Pegou a primeira hora válida e sai
                            # Se não encontrou 'wit_time' na sub-lista, tenta do 'value' principal
                            if 'wit_time' not in entities:
                                if 'T' in wit_time_value and ':' in wit_time_value: # Parece um formato ISO
                                    time_part = wit_time_value.split('T')[1].split(':')[0:2] # Pega HH:MM
                                    entities['wit_time'] = ":".join(time_part)
                                elif re.match(r'^\d{2}:\d{2}$', wit_time_value): # Se já for HH:MM
                                     entities['wit_time'] = wit_time_value
                                else: # Último recurso, tenta parsear como datetime e formatar
                                    dt_object = datetime.fromisoformat(wit_time_value.replace('Z', '+00:00')) 
                                    entities['wit_time'] = dt_object.strftime('%H:%M')
                        except Exception as e:
                            print(f"Erro ao parsear wit_time_obj no parse_wit_ai_response: {wit_time_value}, Erro: {e}")
                            entities['wit_time'] = wit_time_value # Armazena o valor bruto em caso de erro

            elif entity_name_short == 'wit$quantity': # Entidade de quantidade built-in
                if entity_list:
                    # Aqui você vai querer uma lista de todas as quantidades detectadas
                    quantities_found = []
                    for item in entity_list:
                        quantities_found.append({
                            'value': item.get('value'),
                            'unit': item.get('unit'),
                            'product': item.get('product'), # O campo 'product' é muito útil aqui!
                            'raw': item.get('body') # O texto original da entidade
                        })
                    entities['quantity'] = quantities_found # Armazena como uma lista de dicionários

            elif entity_list: # Para suas entidades customizadas como food_item, activity_name, goal_type, reminder_text
                # Se for uma entidade que pode ter múltiplos valores (ex: food_item), armazene todos eles em uma lista
                entities[entity_name_short] = [item.get('value') for item in entity_list if 'value' in item]
                # Ou se for um único valor esperado, pegue o primeiro
                # entities[entity_name_short] = entity_list[0].get('value') # Cuidado se a entidade pode ser múltipla

    return {'intent': main_intent, 'entities': entities}

# Exemplo de uso (para testar localmente)
if __name__ == '__main__':
    # Certifique-se que WIT_AI_SERVER_ACCESS_TOKEN está no seu .env
    test_phrases = [
        "Oi bot",
        "Comi um prato de arroz e feijao",
        "Meu peso e 70.5",
        "Eu corri por 45 minutos",
        "Me da o resumo do dia",
        "Define meta de calorias 1800",
        "Quero um lembrete para beber agua as 15:30",
        "Comi 100g de batata", # Novo teste
        "Comi 250g de maca e 700g de iogurte" # Novo teste
    ]

    for phrase in test_phrases:
        print(f"\nFrase: '{phrase}'")
        wit_resp = get_wit_ai_response(phrase)
        if wit_resp:
            parsed_data = parse_wit_ai_response(wit_resp)
            print(f"Intenção: {parsed_data['intent']}")
            print(f"Entidades: {parsed_data['entities']}")
        else:
            print("Nenhuma resposta do Wit.ai ou erro na requisição.")