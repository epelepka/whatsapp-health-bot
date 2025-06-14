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

# Ensina o Flask a olhar os cabeçalhos do proxy (corrige o erro 403)
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1)

print("3. Flask app criado.") 

# Configurações da Twilio (do .env)
TWILIO_ACCOUNT_SID = os.getenv('TWILIO_ACCOUNT_SID')
TWILIO_AUTH_TOKEN = os.getenv('TWILIO_AUTH_TOKEN')
TWILIO_WHATSAPP_NUMBER = os.getenv('TWILIO_WHATSAPP_NUMBER') 

# Cliente Twilio para enviar mensagens proativas
twilio_client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)

# Inicializa o banco de dados
with app.app_context():
    init_db()
    print("4. Banco de dados inicializado.") 

# --- Funções do Agendador ---
def send_reminder_message(whatsapp_number, reminder_text):
    """Envia uma mensagem de lembrete para o número de WhatsApp."""
    try:
        twilio_client.messages.create(
            from_=TWILIO_WHATSAPP_NUMBER,
            to=whatsapp_number,
            body=f"🔔 Lembrete: {reminder_text}"
        )
        print(f"Lembrete enviado para {whatsapp_number}: {reminder_text}")
    except Exception as e:
        print(f"Erro ao enviar lembrete para {whatsapp_number}: {e}")

def schedule_all_reminders():
    """Agenda todos os lembretes ativos do banco de dados."""
    reminders = get_active_reminders()
    print(f"Agendando {len(reminders)} lembretes...")
    for r in reminders:
        reminder_text, reminder_time_str, whatsapp_number = r['reminder_text'], r['reminder_time'], r['whatsapp_number']
        try:
            hour, minute = map(int, reminder_time_str.split(':'))
            job_id = f"reminder_{whatsapp_number}_{hour:02d}{minute:02d}_{reminder_text.replace(' ', '_')[:10]}"
            scheduler.add_job(
                send_reminder_message,
                CronTrigger(hour=hour, minute=minute),
                args=[whatsapp_number, reminder_text],
                id=job_id,
                replace_existing=True
            )
            print(f"Agendado: {reminder_text} para {whatsapp_number} às {reminder_time_str}")
        except Exception as e:
            print(f"Erro ao agendar lembrete '{reminder_text}' para {whatsapp_number} às {reminder_time_str}: {e}")

def send_good_morning_message():
    """Envia uma mensagem de bom dia para todos os usuários que não interagiram hoje."""
    print("Verificando usuários para enviar mensagem de bom dia...")
    all_users = get_all_users()
    today = date.today()
    for user_number in all_users:
        last_interaction = get_last_interaction_date(user_number)
        if last_interaction is None or last_interaction < today:
            try:
                twilio_client.messages.create(
                    from_=TWILIO_WHATSAPP_NUMBER,
                    to=user_number,
                    body="☀️ Bom dia! Pronto para o dia? Me diga como posso te ajudar hoje."
                )
                print(f"Mensagem de bom dia enviada para {user_number}.")
            except Exception as e:
                print(f"Erro ao enviar bom dia para {user_number}: {e}")
        else:
            print(f"Usuário {user_number} já interagiu hoje. Não enviando bom dia.")

# Inicializa e inicia o agendador
scheduler = BackgroundScheduler()
scheduler.start()
print("5. Agendador iniciado.") 

scheduler.add_job(send_good_morning_message, CronTrigger(hour=8, minute=0), id='daily_good_morning', replace_existing=True)
print("Job de bom dia diário agendado para 08:00.")

atexit.register(lambda: scheduler.shutdown())

with app.app_context():
    schedule_all_reminders()

@app.route("/webhook", methods=['POST'])
def webhook():
    # --- Validação da Requisição da Twilio ---
    validator = RequestValidator(os.environ.get('TWILIO_AUTH_TOKEN'))
    if not validator.validate(request.url, request.form.to_dict(), request.headers.get('X-Twilio-Signature', '')):
        print("!!! VALIDAÇÃO FALHOU !!!")
        return abort(403)
    
    # --- Processamento da Mensagem ---
    incoming_msg = request.values.get('Body', '').strip() 
    from_number = request.values.get('From', '') 
    
    print(f"Mensagem recebida de {from_number}: {incoming_msg}")

    # Atualiza a data da última interação e obtém o estado do usuário
    with app.app_context():
        update_last_interaction_date(from_number)
    user_state = get_user_state(from_number)
    current_state = user_state['state']
    context_data = user_state.get('context_data') or {}
    
    resp = MessagingResponse()
    msg = resp.message()

    # --- Lógica de Máquina de Estados ---

    if current_state == 'awaiting_meal_confirmation':
        answer = incoming_msg.lower().strip()
        meal_context = context_data

        if answer in ['sim', 's', 'ok', 'correto', 'isso']:
            best_guess = meal_context.get('best_guess')
            if best_guess:
                add_food_entry(from_number, best_guess['foods_listed'], best_guess['calories'], best_guess['carbohydrates'], best_guess['proteins'], best_guess['fats'])
                msg.body(f"✅ Ótimo! Salvei '{best_guess['original_alimento']}' no seu diário.")
            else:
                msg.body("🤔 Ocorreu um erro, não consegui encontrar os dados da refeição. Tente de novo.")
            set_user_state(from_number, 'none')

        elif answer in ['não', 'nao', 'n', 'errado', 'outro']:
            alternatives = meal_context.get('alternatives', [])
            if alternatives:
                response_lines = ["Ok. Encontrei estas outras opções para sua busca:"]
                alternatives_map = {}
                for i, food_data in enumerate(alternatives):
                    key = str(i + 1)
                    response_lines.append(f"{key}. {food_data['original_alimento']}")
                    alternatives_map[key] = food_data
                
                response_lines.append("\nPor favor, digite o número da opção correta. Se nenhuma estiver certa, digite 'cancela'.")
                msg.body("\n".join(response_lines))

                set_user_state(from_number, 'awaiting_alternative_selection', context_data={'alternatives_map': alternatives_map})
            else:
                msg.body("❌ Ok, cancelado. Não encontrei outras opções para sua busca.")
                set_user_state(from_number, 'none')
        
        else:
            msg.body("Não entendi. Por favor, responda com 'sim' para confirmar ou 'não' para ver outras opções.")
        
        return str(resp)
    
    # ***** BLOCO FINALMENTE CORRIGIDO *****
    elif current_state == 'awaiting_alternative_selection':
        answer = incoming_msg.lower().strip().replace('.', '')
        alternatives_map = context_data.get('alternatives_map', {})

        if answer in ['cancela', 'cancelar']:
            msg.body("Ok, operação cancelada.")
            set_user_state(from_number, 'none')
            # ADICIONADO RETURN PARA PARAR A EXECUÇÃO
            return str(resp)

        if answer in alternatives_map:
            chosen_food = alternatives_map[answer]
            add_food_entry(from_number, chosen_food['foods_listed'], chosen_food['calories'], chosen_food['carbohydrates'], chosen_food['proteins'], chosen_food['fats'])
            msg.body(f"✅ Certo! Salvei '{chosen_food['original_alimento']}' no seu diário.")
            set_user_state(from_number, 'none')
        else:
            msg.body("Número inválido. Por favor, escolha um número da lista ou digite 'cancela'.")
        
        # ADICIONADO RETURN PARA PARAR A EXECUÇÃO EM TODOS OS CASOS
        return str(resp)

    elif current_state == 'awaiting_meal_delete_number':
        parsed_data = parse_wit_ai_response(incoming_msg) 
        entry_number_list = parsed_data['entities'].get('entry_number', [])
        
        if entry_number_list:
            chosen_index = int(entry_number_list[0]) 
            meal_ids_map = context_data.get('meal_ids_map') 
            
            if meal_ids_map and str(chosen_index) in meal_ids_map:
                if delete_food_entry_by_id(meal_ids_map[str(chosen_index)]) > 0:
                    msg.body(f"Refeição número {chosen_index} excluída com sucesso!")
                else:
                    msg.body("Não foi possível excluir a refeição. Tente novamente.")
            else:
                msg.body("Número de refeição inválido. Por favor, digite um número da lista.")
            
            set_user_state(from_number, 'none')
        else:
            msg.body("Não entendi qual refeição você quer excluir. Por favor, digite apenas o número da refeição na lista (ex: '1').")
        return str(resp) 

    # --- Análise de NLP e Roteamento de Intenção ---
    wit_response = get_wit_ai_response(incoming_msg) 
    parsed_data = parse_wit_ai_response(wit_response)
    intent = parsed_data.get('intent')
    entities = parsed_data.get('entities', {})

    print(f"Intenção detectada: {intent}, Entidades: {entities}")

    # --- LÓGICA PARA CADA INTENÇÃO ---

    if intent == 'registrar_refeicao':
        food_items_list = entities.get('food_item', []) 
        
        if not food_items_list:
            msg.body("Não consegui identificar o que você comeu. Por favor, diga (ex: 'Comi 100g de arroz e 50g de feijão').")
            return str(resp)

        food_query = food_items_list[0]
        
        food_options = search_taco_options(food_query)
        
        if not food_options:
            msg.body(f"Não encontrei dados nutricionais para '{food_query}'. Por favor, tente ser mais específico.")
            return str(resp)

        best_guess = food_options[0]
        alternatives = food_options[1:]

        meal_context = {
            "best_guess": best_guess,
            "alternatives": alternatives,
            "original_query": food_query
        }
        
        # CÓDIGO DE TESTE
        # Monta uma mensagem de teste BEM CURTA
        test_message = "TESTE: Encontrei uma opção. Está correto? (sim/não)"
        msg.body(test_message)
        
        print(f"DEBUG: Enviando mensagem de teste curta: '{test_message}'")

        # O resto da lógica continua igual
        set_user_state(from_number, 'awaiting_meal_confirmation', context_data=meal_context)

    elif intent == 'registrar_peso':
        weight = entities.get('weight_value')
        if weight:
            try:
                add_weight_entry(from_number, float(weight))
                msg.body(f"Peso de {float(weight)} kg registrado com sucesso!")
            except ValueError:
                msg.body("Formato de peso inválido. Por favor, use um número (ex: 75.5).")
        else:
            msg.body("Não consegui encontrar o valor do peso. Por favor, diga seu peso (ex: 'Meu peso é 75.5').")

    # ... (O restante das suas intenções como 'registrar_exercicio', 'obter_resumo_diario', etc., continua aqui) ...
    
    else: # Intenção não reconhecida
        msg.body("Desculpe, não entendi o que você quis dizer.")

    return str(resp)

if __name__ == "__main__":
    print("6. Tentando rodar o aplicativo Flask.") 
    app.run(debug=False, host='0.0.0.0', port=os.environ.get('PORT', 5000))
    print("7. Aplicativo Flask rodando.")
