# wit_nlp.py

import requests
import os
from dotenv import load_dotenv
import re 
from datetime import datetime 

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
        "v": "20240501" 
    }

    try:
        response = requests.get(WIT_AI_API_URL, headers=headers, params=params)
        response.raise_for_status() 
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"Erro ao conectar com Wit.ai: {e}")
        return None
    except Exception as e:
        print(f"Erro inesperado ao processar resposta do Wit.ai: {e}")
        return None

def parse_wit_ai_response(wit_response):
    if not wit_response or 'intents' not in wit_response or not wit_response['intents']:
        if not wit_response['intents'] or wit_response['intents'][0]['confidence'] < 0.7:
             return {'intent': 'none', 'entities': {}}
        main_intent = wit_response['intents'][0]['name']
    else:
        main_intent = wit_response['intents'][0]['name'] 
    
    entities = {}
    
    # Inicializa food_item como uma lista vazia, para poder adicionar itens
    entities['food_item'] = [] 

    if 'entities' in wit_response:
        for entity_full_name, entity_list in wit_response['entities'].items():
            entity_name_short = entity_full_name.split(':')[0] 

            if entity_name_short == 'wit$datetime': 
                if entity_list:
                    wit_time_value = entity_list[0].get('value')
                    
                    if wit_time_value:
                        try:
                            for val in entity_list[0].get('values', []):
                                if val.get('type') == 'value' and 'value' in val:
                                    if re.match(r'^\d{2}:\d{2}$', val['value']):
                                        entities['wit_time'] = val['value'] 
                                    else:
                                        dt_object = datetime.fromisoformat(val['value'].replace('Z', '+00:00'))
                                        entities['wit_time'] = dt_object.strftime('%H:%M')
                                    break 
                            if 'wit_time' not in entities:
                                if 'T' in wit_time_value and ':' in wit_time_value: 
                                    time_part = wit_time_value.split('T')[1].split(':')[0:2] 
                                    entities['wit_time'] = ":".join(time_part)
                                elif re.match(r'^\d{2}:\d{2}$', wit_time_value): 
                                     entities['wit_time'] = wit_time_value
                                else: 
                                    dt_object = datetime.fromisoformat(wit_time_value.replace('Z', '+00:00')) 
                                    entities['wit_time'] = dt_object.strftime('%H:%M')
                        except Exception as e:
                            print(f"Erro ao parsear wit_time_obj no parse_wit_ai_response: {wit_time_value}, Erro: {e}")
                            entities['wit_time'] = wit_time_value 

            elif entity_name_short == 'wit$quantity': # Entidade de quantidade built-in
                if entity_list:
                    quantities_found = []
                    for item in entity_list:
                        quantities_found.append({
                            'value': item.get('value'),
                            'unit': item.get('unit'),
                            'product': item.get('product'), 
                            'raw': item.get('body') 
                        })
                        # --- NOVO: FALLBACK PARA FOOD_ITEM AQUI ---
                        # Se wit/quantity extraiu um 'product', adicione-o como food_item
                        product_from_quantity = item.get('product')
                        if product_from_quantity and product_from_quantity not in entities['food_item']:
                            entities['food_item'].append(product_from_quantity)
                        # --- FIM DO FALLBACK ---

                    entities['quantity'] = quantities_found 

            else: # Para suas entidades customizadas como food_item (se o Wit.ai EXTRAIR), activity_name, etc.
                if entity_list:
                    # Se a entidade for food_item E não foi adicionada pelo fallback da quantity, adiciona
                    if entity_name_short == 'food_item':
                        for item_value in entity_list:
                            food_item_value = item_value.get('value')
                            if food_item_value and food_item_value not in entities['food_item']:
                                entities['food_item'].append(food_item_value)
                    else: # Para outras entidades que não são food_item ou quantity/datetime
                        entities[entity_name_short] = [item.get('value') for item in entity_list if 'value' in item]
    
    return {'intent': main_intent, 'entities': entities}

# Exemplo de uso (para testar localmente)
if __name__ == '__main__':
    # Certifique-se que WIT_AI_SERVER_ACCESS_TOKEN está no seu .env
    test_phrases = [
        "Comi 100g de arroz",
        "Comi 250g de maca e 700g de iogurte",
        "Comi salada", # Teste para food_item sem quantity
        "Meu peso e 70.5",
        "Oi bot"
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