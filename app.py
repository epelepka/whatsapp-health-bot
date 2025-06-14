# app.py
from flask import Flask, request, abort
from twilio.twiml.messaging_response import MessagingResponse
from twilio.rest import Client
import os
from dotenv import load_dotenv
import re
from datetime import datetime, date, time
import json 
from twilio.request_validator import RequestValidator
from werkzeug.middleware.proxy_fix import ProxyFix
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
import atexit 

print("1. Imports carregados.") 

# Importa as funções dos outros arquivos
from database import (init_db, get_or_create_user, add_food_entry, add_weight_entry, 
                      add_exercise_entry, get_daily_summary, set_goal, get_goal, 
                      add_reminder, get_active_reminders, get_user_reminders, 
                      deactivate_reminder, update_last_interaction_date, 
                      get_last_interaction_date, get_all_users, delete_all_food_entries_for_day, 
                      get_food_entries_for_day_indexed, delete_food_entry_by_id, 
                      set_user_state, get_user_state)
from activity_api import calculate_calories_burned
from wit_nlp import get_wit_ai_response, parse_wit_ai_response 
from taco_api import search_taco_options

print("2. Funções do banco de dados e APIs importadas.") 

load_dotenv() 

app = Flask(__name__)
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1)

print("3. Flask app criado.") 

# Configurações da Twilio
TWILIO_ACCOUNT_SID = os.getenv('TWILIO_ACCOUNT_SID')
TWILIO_AUTH_TOKEN = os.getenv('TWILIO_AUTH_TOKEN')
TWILIO_WHATSAPP_NUMBER = os.getenv('TWILIO_WHATSAPP_NUMBER') 

twilio_client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)

# ... (Todo o seu código do agendador continua aqui, sem alterações) ...
scheduler = BackgroundScheduler(timezone="America/Sao_Paulo")
scheduler.start()
print("5. Agendador iniciado.") 

def send_twilio_message(to_number, message_body):
    """Função auxiliar para enviar mensagens assíncronas."""
    try:
        twilio_client.messages.create(
            from_=TWILIO_WHATSAPP_NUMBER,
            to=to_number,
            body=message_body
        )
    except Exception as e:
        print(f"Erro ao enviar mensagem via Twilio Client para {to_number}: {e}")

@app.route("/webhook", methods=['POST'])
def webhook():
    validator = RequestValidator(os.environ.get('TWILIO_AUTH_TOKEN'))
    if not validator.validate(request.url, request.form.to_dict(), request.headers.get('X-Twilio-Signature', '')):
        return abort(403)
    
    incoming_msg = request.values.get('Body', '').strip() 
    from_number = request.values.get('From', '') 
    
    update_last_interaction_date(from_number)
    user_state = get_user_state(from_number)
    current_state = user_state['state']
    context_data = user_state.get('context_data') or {}
    
    wit_response = get_wit_ai_response(incoming_msg)
    parsed_data = parse_wit_ai_response(wit_response)
    intent = parsed_data.get('intent')
    
    interrupting_intents = ['registrar_refeicao', 'registrar_peso', 'definir_meta', 'saudacao']
    if current_state != 'none' and intent in interrupting_intents:
        set_user_state(from_number, 'none')
        current_state = 'none'

    # --- Lógica de Máquina de Estados ---
    
    if current_state == 'awaiting_meal_confirmation':
        resp = MessagingResponse()
        answer = incoming_msg.lower().strip()
        meal_context = context_data

        if answer in ['sim', 's', 'ok', 'correto', 'isso']:
            best_guess = meal_context.get('best_guess')
            if best_guess:
                add_food_entry(from_number, best_guess['foods_listed'], best_guess['calories'], best_guess['carbohydrates'], best_guess['proteins'], best_guess['fats'])
                total_consumed_today = sum(f['calories'] for f in get_daily_summary(from_number)['foods'])
                response_text = f"✅ Salvo! ({best_guess['original_alimento']})\n\nTotal de hoje: {total_consumed_today:.0f} kcal."
                calorie_goal = get_goal(from_number, 'calorie_intake')
                if calorie_goal:
                    remaining = calorie_goal['target_value'] - total_consumed_today
                    response_text += f"\nMeta: {remaining:.0f} kcal restantes."
                send_twilio_message(from_number, response_text) # Envio assíncrono
            set_user_state(from_number, 'none')
        elif answer in ['não', 'nao', 'n', 'errado', 'outro']:
            # ... (Lógica para mostrar alternativas, que já funciona) ...
            alternatives = meal_context.get('alternatives', [])
            if alternatives:
                response_lines = ["Ok. Encontrei estas outras opções:"]
                alternatives_map = {}
                for i, food_data in enumerate(alternatives):
                    key = str(i + 1)
                    response_lines.append(f"{key}. {food_data['original_alimento']}")
                    alternatives_map[key] = food_data
                response_lines.append("\nDigite o número da opção correta ou 'cancela'.")
                resp.message("\n".join(response_lines))
                set_user_state(from_number, 'awaiting_alternative_selection', context_data={'alternatives_map': alternatives_map})
                return str(resp)
            else:
                 resp.message("❌ Ok, cancelado. Não encontrei outras opções.")
                 set_user_state(from_number, 'none')
                 return str(resp)
        else:
            resp.message("Não entendi. Por favor, responda com 'sim' ou 'não'.")
            return str(resp)
        return str(MessagingResponse()) # Retorna resposta vazia após envio assíncrono

    elif current_state == 'awaiting_alternative_selection':
        answer = incoming_msg.lower().strip().replace('.', '')
        alternatives_map = context_data.get('alternatives_map', {})

        if answer in ['cancela', 'cancelar']:
            send_twilio_message(from_number, "Ok, operação cancelada.")
            set_user_state(from_number, 'none')
        elif answer in alternatives_map:
            chosen_food = alternatives_map[answer]
            add_food_entry(from_number, chosen_food['foods_listed'], chosen_food['calories'], chosen_food['carbohydrates'], chosen_food['proteins'], chosen_food['fats'])
            
            total_consumed_today = sum(f['calories'] for f in get_daily_summary(from_number)['foods'])
            response_text = f"✅ Salvo! ({chosen_food['original_alimento']})\n\nTotal de hoje: {total_consumed_today:.0f} kcal."
            calorie_goal = get_goal(from_number, 'calorie_intake')
            if calorie_goal:
                remaining = calorie_goal['target_value'] - total_consumed_today
                response_text += f"\nMeta: {remaining:.0f} kcal restantes."
            
            send_twilio_message(from_number, response_text) # Envio assíncrono
            set_user_state(from_number, 'none')
        else:
            send_twilio_message(from_number, "Número inválido. Escolha um número da lista ou digite 'cancela'.")
        
        return str(MessagingResponse()) # Retorna resposta vazia após envio assíncrono

    # --- Roteamento de Intenção ---
    
    resp = MessagingResponse()
    entities = parsed_data.get('entities', {})

    if intent == 'registrar_refeicao':
        # ... (Lógica para iniciar a busca, que já funciona) ...
        food_items_list = entities.get('food_item', []) 
        if not food_items_list:
            resp.message("Não consegui identificar o que você comeu...")
        else:
            food_query = food_items_list[0]
            food_options = search_taco_options(food_query)
            if not food_options:
                resp.message(f"Não encontrei dados para '{food_query}'.")
            else:
                best_guess = food_options[0]
                alternatives = food_options[1:]
                meal_context = {"best_guess": best_guess, "alternatives": alternatives}
                resp.message(f"Encontrei: {best_guess['original_alimento']}. Está correto? (sim/não)")
                set_user_state(from_number, 'awaiting_meal_confirmation', context_data=meal_context)
    
    # ... (ADICIONE A LÓGICA PARA SUAS OUTRAS INTENÇÕES AQUI) ...
    
    else: # Fallback final
        resp.message("Desculpe, não entendi o que você quis dizer.")

    return str(resp)

if __name__ == "__main__":
    app.run(debug=False, host='0.0.0.0', port=os.environ.get('PORT', 5000))

