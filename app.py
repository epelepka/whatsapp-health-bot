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
TWILIO_ACCOUNT_SID = os.getenv('TWilio_ACCOUNT_SID')
TWILIO_AUTH_TOKEN = os.getenv('TWILIO_AUTH_TOKEN')
TWILIO_WHATSAPP_NUMBER = os.getenv('TWILIO_WHATSAPP_NUMBER') 

twilio_client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)

# Inicializa o banco de dados e o agendador
with app.app_context():
    init_db()
print("4. Banco de dados inicializado.") 

scheduler = BackgroundScheduler(timezone="America/Sao_Paulo")
# ... (suas funções de agendador como send_reminder_message, etc. continuam aqui, sem alterações) ...
scheduler.start()
print("5. Agendador iniciado.") 

# --- NOVA FUNÇÃO AUXILIAR PARA ENVIAR MÚLTIPLAS MENSAGENS ---
def send_post_meal_summary(user_number, added_meal_data):
    """Envia uma sequência de mensagens de resumo após registrar uma refeição."""
    try:
        # Mensagem 1: Confirmação simples
        twilio_client.messages.create(
            from_=TWILIO_WHATSAPP_NUMBER,
            to=user_number,
            body=f"✅ Ótimo! Salvei '{added_meal_data['original_alimento']}' no seu diário."
        )

        # Mensagem 2: Detalhes da refeição adicionada
        summary_meal = (
            f"Detalhes da refeição adicionada:\n"
            f"Calorias: {added_meal_data['calories']:.0f} kcal\n"
            f"Carboidratos: {added_meal_data['carbohydrates']:.0f} g\n"
            f"Proteínas: {added_meal_data['proteins']:.0f} g\n"
            f"Gorduras: {added_meal_data['fats']:.0f} g"
        )
        twilio_client.messages.create(from_=TWILIO_WHATSAPP_NUMBER, to=user_number, body=summary_meal)

        # Mensagem 3: Resumo do dia e status da meta
        daily_summary = get_daily_summary(user_number)
        total_consumed_today = sum(f['calories'] for f in daily_summary['foods'])
        
        calorie_goal = get_goal(user_number, 'calorie_intake')
        
        if calorie_goal:
            remaining_calories = calorie_goal['target_value'] - total_consumed_today
            if remaining_calories >= 0:
                summary_day = f"Resumo de hoje: Você já consumiu {total_consumed_today:.0f} kcal. Ainda pode consumir {remaining_calories:.0f} kcal para atingir sua meta de {calorie_goal['target_value']:.0f} kcal."
            else:
                summary_day = f"🚨 Atenção! Resumo de hoje: Você já consumiu {total_consumed_today:.0f} kcal e excedeu sua meta diária em {-remaining_calories:.0f} kcal."
        else:
            summary_day = f"Resumo de hoje: Você já consumiu {total_consumed_today:.0f} kcal. Defina uma meta para acompanharmos juntos! (ex: 'Definir meta 2000')."
            
        twilio_client.messages.create(from_=TWILIO_WHATSAPP_NUMBER, to=user_number, body=summary_day)

    except Exception as e:
        print(f"Erro ao enviar resumo para {user_number}: {e}")

@app.route("/webhook", methods=['POST'])
def webhook():
    # Validação da Twilio
    validator = RequestValidator(os.environ.get('TWILIO_AUTH_TOKEN'))
    if not validator.validate(request.url, request.form.to_dict(), request.headers.get('X-Twilio-Signature', '')):
        return abort(403)
    
    incoming_msg = request.values.get('Body', '').strip() 
    from_number = request.values.get('From', '') 
    
    update_last_interaction_date(from_number)
    user_state = get_user_state(from_number)
    current_state = user_state['state']
    context_data = user_state.get('context_data') or {}
    
    # Análise de NLP feita uma vez no início
    wit_response = get_wit_ai_response(incoming_msg)
    parsed_data = parse_wit_ai_response(wit_response)
    intent = parsed_data.get('intent')
    
    # Lógica de Reset Inteligente
    interrupting_intents = ['registrar_refeicao', 'registrar_peso', 'saudacao'] # etc.
    if current_state != 'none' and intent in interrupting_intents:
        set_user_state(from_number, 'none')
        current_state = 'none'

    # --- Lógica de Máquina de Estados ---
    
    if current_state == 'awaiting_meal_confirmation':
        answer = incoming_msg.lower().strip()
        meal_context = context_data

        if answer in ['sim', 's', 'ok', 'correto', 'isso']:
            best_guess = meal_context.get('best_guess')
            if best_guess:
                add_food_entry(from_number, best_guess['foods_listed'], best_guess['calories'], best_guess['carbohydrates'], best_guess['proteins'], best_guess['fats'])
                # CHAMA A NOVA FUNÇÃO DE RESUMO
                send_post_meal_summary(from_number, best_guess)
            set_user_state(from_number, 'none')
        elif answer in ['não', 'nao', 'n', 'errado', 'outro']:
            alternatives = meal_context.get('alternatives', [])
            if alternatives:
                resp = MessagingResponse()
                msg = resp.message()
                response_lines = ["Ok. Encontrei estas outras opções:"]
                alternatives_map = {}
                for i, food_data in enumerate(alternatives):
                    key = str(i + 1)
                    response_lines.append(f"{key}. {food_data['original_alimento']}")
                    alternatives_map[key] = food_data
                response_lines.append("\nDigite o número da opção correta ou 'cancela'.")
                msg.body("\n".join(response_lines))
                set_user_state(from_number, 'awaiting_alternative_selection', context_data={'alternatives_map': alternatives_map})
                return str(resp)
            else:
                resp = MessagingResponse()
                resp.message("❌ Ok, cancelado. Não encontrei outras opções.")
                set_user_state(from_number, 'none')
                return str(resp)
        else:
            resp = MessagingResponse()
            resp.message("Não entendi. Por favor, responda com 'sim' ou 'não'.")
            return str(resp)

    elif current_state == 'awaiting_alternative_selection':
        answer = incoming_msg.lower().strip().replace('.', '')
        alternatives_map = context_data.get('alternatives_map', {})

        if answer in ['cancela', 'cancelar']:
            resp = MessagingResponse()
            resp.message("Ok, operação cancelada.")
            set_user_state(from_number, 'none')
            return str(resp)

        if answer in alternatives_map:
            chosen_food = alternatives_map[answer]
            add_food_entry(from_number, chosen_food['foods_listed'], chosen_food['calories'], chosen_food['carbohydrates'], chosen_food['proteins'], chosen_food['fats'])
            # CHAMA A NOVA FUNÇÃO DE RESUMO
            send_post_meal_summary(from_number, chosen_food)
            set_user_state(from_number, 'none')
        else:
            resp = MessagingResponse()
            resp.message("Número inválido. Escolha um número da lista ou 'cancela'.")
            return str(resp)
    
    # ... (outros estados como 'awaiting_meal_delete_number' continuam aqui) ...
            
    # --- Roteamento de Intenção ---
    elif intent == 'registrar_refeicao':
        food_items_list = parsed_data['entities'].get('food_item', []) 
        if not food_items_list:
            resp = MessagingResponse()
            resp.message("Não consegui identificar o que você comeu...")
            return str(resp)
        
        food_query = food_items_list[0]
        food_options = search_taco_options(food_query)
        
        if not food_options:
            resp = MessagingResponse()
            resp.message(f"Não encontrei dados para '{food_query}'.")
            return str(resp)

        best_guess = food_options[0]
        alternatives = food_options[1:]
        meal_context = {"best_guess": best_guess, "alternatives": alternatives}
        
        resp = MessagingResponse()
        # Envia uma mensagem curta para evitar o limite de caracteres
        resp.message(f"Encontrei: {best_guess['original_alimento']}. Está correto? (sim/não)")
        set_user_state(from_number, 'awaiting_meal_confirmation', context_data=meal_context)
        return str(resp)
        
    # ... (O restante de suas intenções: 'registrar_peso', 'obter_resumo_diario', etc. continuam aqui) ...
    
    # Se chegamos até aqui, significa que a mensagem foi proativa ou a intenção não precisa de uma resposta síncrona.
    # Retorna uma resposta vazia para Twilio para evitar erro.
    return str(MessagingResponse())

if __name__ == "__main__":
    app.run(debug=False, host='0.0.0.0', port=os.environ.get('PORT', 5000))

