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
from taco_api import get_taco_nutrition 

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

# --- Funções do Agendador (CORRIGIDAS) ---

def _get_job_id(whatsapp_number, reminder_text, reminder_time_str):
    """Cria um ID de job único e previsível."""
    hour, minute = map(int, reminder_time_str.split(':'))
    # Remove caracteres inválidos para o ID
    safe_text = re.sub(r'\W+', '', reminder_text.replace(' ', '_'))
    return f"reminder_{whatsapp_number}_{hour:02d}{minute:02d}_{safe_text[:20]}"

def send_reminder_message(whatsapp_number, reminder_text):
    """Envia uma mensagem de lembrete (com contexto do app)."""
    with app.app_context():
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
    """Agenda todos os lembretes ativos do banco de dados (com contexto do app)."""
    with app.app_context():
        reminders = get_active_reminders()
        print(f"Agendando {len(reminders)} lembretes...")
        for r in reminders:
            reminder_text, reminder_time_str, whatsapp_number = r['reminder_text'], r['reminder_time'], r['whatsapp_number']
            try:
                hour, minute = map(int, reminder_time_str.split(':'))
                job_id = _get_job_id(whatsapp_number, reminder_text, reminder_time_str)
                scheduler.add_job(
                    send_reminder_message,
                    CronTrigger(hour=hour, minute=minute),
                    args=[whatsapp_number, reminder_text],
                    id=job_id,
                    replace_existing=True
                )
                print(f"Agendado: {reminder_text} para {whatsapp_number} às {reminder_time_str}")
            except Exception as e:
                print(f"Erro ao agendar lembrete '{reminder_text}': {e}")

def send_good_morning_message():
    """Envia uma mensagem de bom dia (com contexto do app)."""
    with app.app_context():
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

# Inicializa e inicia o agendador
scheduler = BackgroundScheduler(timezone="America/Sao_Paulo")
scheduler.start()
print("5. Agendador iniciado.") 

scheduler.add_job(send_good_morning_message, CronTrigger(hour=8, minute=0), id='daily_good_morning', replace_existing=True)
print("Job de bom dia diário agendado para 08:00.")

atexit.register(lambda: scheduler.shutdown())

schedule_all_reminders()

@app.route("/webhook", methods=['POST'])
def webhook():
    # --- Validação da Requisição da Twilio (CORRIGIDO) ---
    validator = RequestValidator(os.environ.get('TWILIO_AUTH_TOKEN'))
    if not validator.validate(request.url, request.form.to_dict(), request.headers.get('X-Twilio-Signature', '')):
        print("!!! VALIDAÇÃO FALHOU !!!")
        return abort(403)
    
    # --- Processamento da Mensagem (CORRIGIDO) ---
    incoming_msg = request.values.get('Body', '').strip() 
    from_number = request.values.get('From', '') 
    
    print(f"Mensagem recebida de {from_number}: {incoming_msg}")

    update_last_interaction_date(from_number)
    user_state = get_user_state(from_number)
    
    resp = MessagingResponse()
    msg = resp.message()

      resp = MessagingResponse()
    msg = resp.message()

    # --- NOVO TRATADOR DE ESTADO PARA CONFIRMAÇÃO DE REFEIÇÃO ---
    if current_state == 'awaiting_meal_confirmation':
        answer = incoming_msg.lower().strip()
        meal_context = context_data

        if answer in ['sim', 's', 'ok', 'correto', 'isso']:
            # Usuário confirmou, agora salvamos no banco
            if meal_context:
                add_food_entry(
                    from_number,
                    meal_context['db_description'],
                    meal_context['calories'],
                    meal_context['carbohydrates'],
                    meal_context['proteins'],
                    meal_context['fats']
                )
                msg.body("✅ Ótimo! Refeição registrada no seu diário.")
            else:
                msg.body("🤔 Ocorreu um erro, não consegui encontrar os dados da refeição para salvar. Por favor, tente registrar novamente.")
            
            set_user_state(from_number, 'none') # Limpa o estado

        elif answer in ['não', 'nao', 'n', 'errado', 'cancelar']:
            # Usuário cancelou
            msg.body("❌ Ok, refeição cancelada. O que você gostaria de registrar então?")
            set_user_state(from_number, 'none') # Limpa o estado
        
        else:
            # Resposta não reconhecida, pede para tentar de novo
            msg.body("Não entendi. Por favor, responda com 'sim' para confirmar ou 'não' para cancelar a refeição.")
            # Mantém o estado para a próxima tentativa
        
        return str(resp) # Envia a resposta e termina a execução aqui

    # O resto do seu código continua a partir daqui...
    if current_state == 'awaiting_meal_delete_number':
        # ...

    # --- Lógica de Máquina de Estados (ex: para exclusão de refeição) ---
    if user_state['state'] == 'awaiting_meal_delete_number':
        parsed_data = parse_wit_ai_response(incoming_msg) 
        entry_number_list = parsed_data['entities'].get('entry_number', [])
        
        if entry_number_list:
            chosen_index = int(entry_number_list[0]) 
            meal_ids_map = user_state['context_data'].get('meal_ids_map') 
            
            if meal_ids_map and chosen_index in meal_ids_map:
                if delete_food_entry_by_id(meal_ids_map[chosen_index]) > 0:
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
    parsed_data = parse_wit_ai_response(incoming_msg)
    intent = parsed_data.get('intent')
    entities = parsed_data.get('entities', {})

    print(f"Intenção detectada: {intent}, Entidades: {entities}")

    # --- LÓGICA PARA CADA INTENÇÃO ---

    if intent == 'registrar_refeicao':
        food_items_list = entities.get('food_item', []) 
        
        if not food_items_list:
            msg.body("Não consegui identificar o que você comeu. Por favor, diga (ex: 'Comi 100g de arroz e 50g de feijão').")
            return str(resp)

        total_meal_calories, total_meal_carbs, total_meal_proteins, total_meal_fats = 0, 0, 0, 0
        foods_for_db = [] 
        response_lines_for_display = []
        
        # Itera sobre os alimentos identificados pelo Wit.ai
        for food_query in food_items_list:
            taco_data = get_taco_nutrition(food_query) # Chama a busca apenas uma vez por item
            
            if taco_data and taco_data['calories'] > 0:
                total_meal_calories += taco_data['calories']
                total_meal_carbs += taco_data['carbohydrates']
                total_meal_proteins += taco_data['proteins']
                total_meal_fats += taco_data['fats']
                foods_for_db.append(taco_data['foods_listed']) 
                response_lines_for_display.append(
                    f"- {taco_data['foods_listed']} (Cal: {taco_data['calories']:.0f} | "
                    f"Carb: {taco_data['carbohydrates']:.0f} | Prot: {taco_data['proteins']:.0f} | "
                    f"Gord: {taco_data['fats']:.0f})"
                )
        
        if not response_lines_for_display:
            msg.body(f"Não encontrei dados nutricionais para '{incoming_msg}'. Por favor, tente ser mais específico.")
            return str(resp)
            # --- NOVA LÓGICA DE CONFIRMAÇÃO ---
        
        # Prepara os dados para salvar, mas ainda não salva
        meal_context = {
            "db_description": ", ".join(foods_for_db),
            "calories": total_meal_calories,
            "carbohydrates": total_meal_carbs,
            "proteins": total_meal_proteins,
            "fats": total_meal_fats
        }

        # Monta a mensagem de confirmação para o usuário
        final_response_parts = ["Entendi o seguinte:"]
        final_response_parts.extend(response_lines_for_display)
        final_response_parts.append(f"\nTotal: {total_meal_calories:.0f} kcal, {total_meal_carbs:.0f}g Carb, {total_meal_proteins:.0f}g Prot, {total_meal_fats:.0f}g Gord.")
        final_response_parts.append("\nEstá correto? Responda com 'sim' para salvar ou 'não' para cancelar.")
        
        msg.body("\n".join(final_response_parts))

        # Define o novo estado e salva o contexto da refeição
        set_user_state(from_number, 'awaiting_meal_confirmation', context_data=meal_context)

        add_food_entry(from_number, ", ".join(foods_for_db), total_meal_calories, total_meal_carbs, total_meal_proteins, total_meal_fats)
        
        final_response_parts = ["Refeição registrada:"] + response_lines_for_display
        final_response_parts.append(f"\nTotal da refeição: {total_meal_calories:.0f} kcal, {total_meal_carbs:.0f}g Carb, {total_meal_proteins:.0f}g Prot, {total_meal_fats:.0f}g Gord.")

        calorie_goal = get_goal(from_number, 'calorie_intake')
        if calorie_goal:
            total_consumed_today = sum(f['calories'] for f in get_daily_summary(from_number)['foods']) 
            remaining_calories = calorie_goal['target_value'] - total_consumed_today
            if remaining_calories >= 0:
                final_response_parts.append(f"Você ainda pode consumir {remaining_calories:.0f} kcal hoje para atingir sua meta de {calorie_goal['target_value']:.0f} kcal.")
            else:
                final_response_parts.append(f"🚨 Atenção: Você já excedeu sua meta diária de {calorie_goal['target_value']:.0f} kcal em {-remaining_calories:.0f} kcal.")
        else:
            final_response_parts.append("\nDefina uma meta de calorias diárias para saber quantas calorias ainda pode consumir (ex: 'Definir meta calorias 2000').")
        
        msg.body("\n".join(final_response_parts))

    elif intent == 'registrar_peso':
        weight = entities.get('weight_value')
        if weight:
            try:
                add_weight_entry(from_number, float(weight))
                msg.body(f"Peso de {float(weight)} kg registrado com sucesso!")
            except (ValueError, TypeError):
                msg.body("Formato de peso inválido. Por favor, use um número (ex: 75.5).")
        else:
            msg.body("Não consegui encontrar o valor do peso. Por favor, diga seu peso (ex: 'Meu peso é 75.5').")

    elif intent == 'excluir_refeicao_especifica':
        entry_number_list = entities.get('entry_number', [])
        if entry_number_list: 
            chosen_index = int(entry_number_list[0]) 
            current_meals = get_food_entries_for_day_indexed(from_number)
            meal_ids_map = { (i+1): meal['id'] for i, meal in enumerate(current_meals) }
            if meal_ids_map and chosen_index in meal_ids_map:
                if delete_food_entry_by_id(meal_ids_map[chosen_index]) > 0:
                    msg.body(f"Refeição número {chosen_index} excluída com sucesso!")
                else:
                    msg.body("Não foi possível excluir a refeição. Tente novamente.")
            else:
                msg.body("Número de refeição inválido. Por favor, digite um número que esteja na sua lista de refeições do dia.")
            set_user_state(from_number, 'none')
        else:
            meals_today = get_food_entries_for_day_indexed(from_number)
            if not meals_today:
                msg.body("Você não tem nenhuma refeição registrada hoje para excluir.")
                set_user_state(from_number, 'none')
            else:
                response_lines = ["Suas refeições de hoje:"]
                meal_ids_map = {} 
                for i, meal in enumerate(meals_today):
                    response_lines.append(f"{i+1}: {meal['foods_description']} ({meal['calories']:.0f} kcal)")
                    meal_ids_map[i+1] = meal['id'] 
                response_lines.append("\nQual refeição você quer excluir? Por favor, envie APENAS o número (ex: '1').")
                set_user_state(from_number, 'awaiting_meal_delete_number', meal_ids_map)
                msg.body("\n".join(response_lines))
    
    elif intent == 'definir_lembrete':
        reminder_text_list = entities.get('reminder_text', [])
        wit_time_obj = entities.get('wit_time') 
        reminder_text = reminder_text_list[0] if reminder_text_list else None
        reminder_time_str = None
        if wit_time_obj:
            try:
                # Tenta extrair HH:MM de formatos como '2025-06-14T10:00:00.000-03:00'
                time_part = wit_time_obj.split('T')[1]
                reminder_time_str = ":".join(time_part.split(':')[0:2])
            except (IndexError, AttributeError):
                reminder_time_str = None # Se falhar, continua para a próxima verificação

        if reminder_text and reminder_time_str:
            if add_reminder(from_number, reminder_text, reminder_time_str):
                hour, minute = map(int, reminder_time_str.split(':'))
                job_id = _get_job_id(from_number, reminder_text, reminder_time_str)
                scheduler.add_job(send_reminder_message, CronTrigger(hour=hour, minute=minute), args=[from_number, reminder_text], id=job_id, replace_existing=True)
                msg.body(f"Lembrete '{reminder_text}' definido para às {reminder_time_str}.")
            else:
                 msg.body("Não consegui definir o lembrete. Talvez já exista um com esse texto e hora.")
        else:
            msg.body("Não consegui identificar o texto ou a hora do lembrete. Use 'Definir lembrete [texto] às [HH:MM]' (ex: 'Definir lembrete beber agua às 10:00').")

    elif intent == 'desativar_lembrete': 
        reminder_text_list = entities.get('reminder_text', [])
        wit_time_obj = entities.get('wit_time')
        reminder_text = reminder_text_list[0] if reminder_text_list else None
        reminder_time_str = None
        if wit_time_obj:
            try:
                time_part = wit_time_obj.split('T')[1]
                reminder_time_str = ":".join(time_part.split(':')[0:2])
            except (IndexError, AttributeError):
                reminder_time_str = None

        if reminder_text and reminder_time_str:
            job_id = _get_job_id(from_number, reminder_text, reminder_time_str)
            if deactivate_reminder(from_number, reminder_text, reminder_time_str):
                if scheduler.get_job(job_id):
                    scheduler.remove_job(job_id)
                msg.body(f"Lembrete '{reminder_text}' às {reminder_time_str} desativado com sucesso.")
            else:
                msg.body("Não encontrei esse lembrete para desativar. Verifique o texto e a hora.")
        else:
            msg.body("Não consegui identificar o texto ou a hora do lembrete a desativar. Use 'Desativar lembrete [texto] às [HH:MM]'.")

    # ... Adicione aqui os outros 'elif' para 'listar_lembretes', 'saudacao', etc. que já funcionavam ...
    # Exemplo:
    elif intent == 'saudacao': 
        msg.body("Olá! Eu sou seu assistente de saúde. Como posso te ajudar hoje?")
    
    else: # Intenção não reconhecida
        msg.body("Desculpe, não entendi o que você quis dizer. Por favor, tente de outra forma.")

    return str(resp)

if __name__ == "__main__":
    print("6. Tentando rodar o aplicativo Flask.") 
    app.run(debug=False, host='0.0.0.0', port=os.environ.get('PORT', 5000))
    print("7. Aplicativo Flask rodando.")