# app.py
from flask import Flask, request
from twilio.twiml.messaging_response import MessagingResponse
from twilio.rest import Client
import os
from dotenv import load_dotenv
import re
from datetime import datetime, date, time
import json 

print("1. Imports carregados.") 

# Importa as funções que criaremos
from database import init_db, get_or_create_user, add_food_entry, add_weight_entry, add_exercise_entry, get_daily_summary, \
                     set_goal, get_goal, add_reminder, get_active_reminders, get_user_reminders, deactivate_reminder, \
                     update_last_interaction_date, get_last_interaction_date, get_all_users, \
                     delete_all_food_entries_for_day, get_food_entries_for_day_indexed, delete_food_entry_by_id, \
                     set_user_state, get_user_state 
from activity_api import calculate_calories_burned
from wit_nlp import get_wit_ai_response, parse_wit_ai_response 
from taco_api import get_taco_nutrition 

print("2. Funções do banco de dados e APIs importadas.") 

# Para agendamento de tarefas
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
import atexit 

load_dotenv() 

app = Flask(__name__)

print("3. Flask app criado.") 

# Configurações da Twilio (do .env)
TWILIO_ACCOUNT_SID = os.getenv('TWILIO_ACCOUNT_SID')
TWILIO_AUTH_TOKEN = os.getenv('TWILIO_AUTH_TOKEN')
TWILIO_WHATSAPP_NUMBER = os.getenv('TWILIO_WHATSAPP_NUMBER') 

# Cliente Twilio para enviar mensagens proativas (para os lembretes e bom dia)
twilio_client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)

# Inicializa o banco de dados ao iniciar o aplicativo
with app.app_context():
    init_db()
    print("4. Banco de dados inicializado.") 

# --- Funções do Agendador de Lembretes ---
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
        reminder_text = r['reminder_text']
        reminder_time_str = r['reminder_time']
        whatsapp_number = r['whatsapp_number']

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

# --- Função para a Mensagem de Bom Dia ---
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

# Adiciona o job diário de "Bom dia" às 8:00
scheduler.add_job(
    send_good_morning_message,
    CronTrigger(hour=8, minute=0), # Todos os dias às 08:00
    id='daily_good_morning',
    replace_existing=True
)
print("Job de bom dia diário agendado para 08:00.")


# Garante que o agendador é desligado quando o Flask app encerra
atexit.register(lambda: scheduler.shutdown())

# Agenda os lembretes existentes ao iniciar o app
with app.app_context():
    schedule_all_reminders()

@app.route("/webhook", methods=['POST'])
def whatsapp_webhook():
    incoming_msg = request.values.get('Body', '') 
    from_number = request.values.get('From', '') 
    user_id = get_or_create_user(from_number) # Obtém o ID do usuário para o estado

    resp = MessagingResponse()
    msg = resp.message()

    print(f"Mensagem recebida de {from_number}: {incoming_msg}")

    with app.app_context():
        update_last_interaction_date(from_number)

    user_state = get_user_state(from_number)
    current_state = user_state['state']
    context_data = user_state['context_data']

    if current_state == 'awaiting_meal_delete_number':
        parsed_data = parse_wit_ai_response(incoming_msg) 
        entry_number_list = parsed_data['entities'].get('entry_number', [])
        
        if entry_number_list:
            chosen_index = int(entry_number_list[0]) 
            
            meal_ids_map = context_data.get('meal_ids_map') 
            
            if meal_ids_map and chosen_index in meal_ids_map:
                meal_id_to_delete = meal_ids_map[chosen_index]
                deleted_rows = delete_food_entry_by_id(meal_id_to_delete)
                
                if deleted_rows > 0:
                    msg.body(f"Refeição número {chosen_index} excluída com sucesso!")
                else:
                    msg.body("Não foi possível excluir a refeição. Tente novamente.")
            else:
                msg.body("Número de refeição inválido. Por favor, digite um número da lista.")
            
            set_user_state(from_number, 'none')
            return str(resp) 
        else:
            msg.body("Não entendi qual refeição você quer excluir. Por favor, digite apenas o número da refeição na lista (ex: '1').")
            return str(resp) 

    wit_response = get_wit_ai_response(incoming_msg) 
    parsed_data = parse_wit_ai_response(wit_response)
    
    intent = parsed_data['intent']
    entities = parsed_data['entities']

    print(f"Intenção detectada: {intent}, Entidades: {entities}")

    if intent == 'registrar_peso':
        weight = entities.get('weight_value')
        if weight:
            try:
                weight = float(weight)
                add_weight_entry(from_number, weight)
                msg.body(f"Peso de {weight} kg registrado com sucesso!")
            except ValueError:
                msg.body("Formato de peso inválido. Por favor, use um número (ex: 75.5).")
        else:
            msg.body("Não consegui encontrar o valor do peso. Por favor, diga seu peso (ex: 'Meu peso é 75.5').")

    elif intent == 'registrar_refeicao':
        food_items_list = entities.get('food_item', []) 
        quantities_list = entities.get('quantity', []) 

        if food_items_list or quantities_list: 
            total_meal_calories = 0
            total_meal_carbs = 0
            total_meal_proteins = 0
            total_meal_fats = 0
            foods_for_db = [] 
            
            response_lines = ["Refeição registrada:"] 
            
            queries_for_taco = []
            
            unique_food_names_from_entities = set() 
            for food_name in food_items_list:
                unique_food_names_from_entities.add(food_name.lower())
            
            for q_item in quantities_list:
                product_name = q_item.get('product')
                if product_name:
                    unique_food_names_from_entities.add(product_name.lower())
            
            for name in unique_food_names_from_entities:
                queries_for_taco.append(name)

            for q_item in quantities_list:
                value = q_item.get('value')
                unit = q_item.get('unit')
                product_name = q_item.get('product') 

                if value and unit and product_name:
                    queries_for_taco.append(f"{value}{unit} de {product_name}") 
                    queries_for_taco.append(f"{value} {unit} de {product_name}") 
                    queries_for_taco.append(f"{value}{unit} {product_name}")     
                elif q_item.get('raw'): 
                    queries_for_taco.append(q_item['raw'])
            
            final_queries = []
            seen_queries = set()
            for q in queries_for_taco:
                normalized_q = q.lower()
                if normalized_q not in seen_queries:
                    final_queries.append(q)
                    seen_queries.add(normalized_q)
            
            final_queries.sort(key=lambda x: (
                1 if x.lower() in unique_food_names_from_entities else 0, 
                len(x) 
            ), reverse=True) 

            print(f"Consultando TACO com: {final_queries}") 

            if not final_queries: 
                msg.body("Não consegui identificar o que você comeu. Por favor, diga (ex: 'Comi arroz e feijão').")
                return str(resp)

            items_found_original_names = set() 
            response_lines_for_display = [] 
            
            for item_query in final_queries:
                taco_data = get_taco_nutrition(item_query) 
                
                if taco_data and taco_data['calories'] > 0 and taco_data['original_alimento'].lower() not in items_found_original_names:
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
                    items_found_original_names.add(taco_data['original_alimento'].lower()) 
                else:
                    is_redundant_message = False
                    base_name_from_query = _get_base_food_name_from_query_string(item_query)
                    
                    for found_original_name in items_found_original_names:
                        if base_name_from_query and (base_name_from_query in found_original_name or found_original_name in base_name_from_query):
                            is_redundant_message = True
                            break
                    
                    if not is_redundant_message:
                        response_lines_for_display.append(f"- Não encontrei dados nutricionais para '{item_query}' na TACO.")
            
            db_description = ", ".join(foods_for_db) if foods_for_db else "Itens não processados"
            
            add_food_entry(
                from_number,
                db_description, 
                total_meal_calories,
                total_meal_carbs,
                total_meal_proteins,
                total_meal_fats
            )
            
            calorie_goal = get_goal(from_number, 'calorie_intake')
            summary = get_daily_summary(from_number) 
            total_consumed_today = sum(f['calories'] for f in summary['foods']) 

            final_response = "\n".join(response_lines_for_display)
            final_response += f"\n\nTotal da refeição: {total_meal_calories:.0f} kcal, {total_meal_carbs:.0f}g Carb, {total_meal_proteins:.0f}g Prot, {total_meal_fats:.0f}g Gord."

            if calorie_goal:
                remaining_calories = calorie_goal['target_value'] - total_consumed_today
                if remaining_calories >= 0:
                    final_response += f"\nVocê ainda pode consumir {remaining_calories:.0f} kcal hoje para atingir sua meta de {calorie_goal['target_value']:.0f} kcal."
                else:
                    final_response += f"\n🚨 Atenção: Você já excedeu sua meta diária de {calorie_goal['target_value']:.0f} kcal em {-remaining_calories:.0f} kcal."
            else:
                final_response += "\nDefina uma meta de calorias diárias para saber quantas calorias ainda pode consumir (ex: 'Definir meta calorias 2000')."
            
            msg.body(final_response)

        else: 
            msg.body("Não consegui identificar o que você comeu. Por favor, diga (ex: 'Comi arroz e feijão').")

    elif intent == 'registrar_exercicio':
        activity_name_list = entities.get('activity_name', []) 
        duration_value = entities.get('duration_value')
        duration_unit_list = entities.get('duration_unit', []) 

        activity_name = activity_name_list[0] if activity_name_list else None
        duration_unit = duration_unit_list[0] if duration_unit_list else None


        if activity_name and duration_value and duration_unit:
            try:
                duration_minutes = int(duration_value)
                if duration_unit.lower() in ['horas', 'hr', 'hora']: 
                    duration_minutes *= 60

                summary_for_weight = get_daily_summary(from_number)
                user_weight_kg = summary_for_weight['last_weight'] if summary_for_weight['last_weight'] else 70

                calories_burned = calculate_calories_burned(activity_name, duration_minutes, user_weight_kg)

                if calories_burned > 0:
                    add_exercise_entry(from_number, activity_name, duration_minutes, calories_burned)
                    msg.body(f"Registrado: {activity_name} por {duration_value} {duration_unit}. Calorias queimadas estimadas: {calories_burned:.2f}.")
                else:
                    msg.body(f"Não consegui estimar as calorias para '{activity_name}'. Tente um exercício mais comum.")
            except ValueError:
                msg.body("Formato de duração inválido. Use números (ex: '30 minutos').")
        else:
            msg.body("Não consegui identificar o exercício ou a duração. Use 'Fiz [exercício] por [tempo]' (ex: 'Fiz corrida por 30 minutos').")

    elif intent == 'obter_resumo_diario':
        summary = get_daily_summary(from_number)
        if summary:
            food_summary = []
            total_food_calories = 0
            total_food_carbs = 0
            total_food_proteins = 0
            total_food_fats = 0

            for f in summary['foods']:
                food_summary.append(f"- {f['foods_description']} (Cal: {f['calories']:.0f} | Carb: {f['carbohydrates']:.0f} | Prot: {f['proteins']:.0f} | Gord: {f['fats']:.0f})")
                total_food_calories += f['calories']
                total_food_carbs += f['carbohydrates']
                total_food_proteins += f['proteins']
                total_food_fats += f['fats']
            
            food_summary_text = "\n".join(food_summary) if food_summary else 'Nenhum alimento registrado.'

            exercise_summary = "\n".join([f"- {e['activity_name']} por {e['duration_minutes']} min ({e['calories_burned']:.2f} kcal) queimadas" for e in summary['exercises']])
            weight_info = f"Seu último peso registrado: {summary['last_weight']:.1f} kg" if summary['last_weight'] else "Nenhum peso registrado."
            total_calories_burned = sum(e['calories_burned'] for e in summary['exercises'])

            response_text = (
                f"Resumo do dia para {from_number}:\n\n"
                f"--- Alimentação ({total_food_calories:.2f} kcal) ---\n"
                f"{food_summary_text}\n"
                f"(Total Carb: {total_food_carbs:.0f}g | Prot: {total_food_proteins:.0f}g | Gord: {total_food_fats:.0f}g)\n\n"
                f"--- Exercícios ({total_calories_burned:.2f} kcal queimadas) ---\n"
                f"{exercise_summary if exercise_summary else 'Nenhum exercício registrado.'}\n\n"
                f"{weight_info}\n\n"
                f"Balanço calórico estimado: {total_food_calories - total_calories_burned:.2f} kcal (Calorias Consumidas - Calorias Queimadas)"
            )
            msg.body(response_text)
        else:
            msg.body("Nenhum registro encontrado para hoje.")

    elif intent == 'listar_refeicoes': 
        summary = get_daily_summary(from_number)
        food_summary_list = summary['foods']
        
        if food_summary_list:
            response_lines = ["Suas refeições de hoje:"]
            total_calories_consumed = 0
            for food_entry in food_summary_list:
                food_description = food_entry['foods_description']
                calories = food_entry['calories']
                carbs = food_entry['carbohydrates']
                proteins = food_entry['proteins']
                fats = food_entry['fats']

                response_lines.append(
                    f"- {food_description} (Cal: {calories:.0f} | Carb: {carbs:.0f} | Prot: {proteins:.0f} | Gord: {fats:.0f})"
                )
                total_calories_consumed += calories
            response_lines.append(f"\nTotal de calorias consumidas hoje: {total_calories_consumed:.2f} kcal.")
            msg.body("\n".join(response_lines))
        else:
            msg.body("Você ainda não registrou nenhuma refeição hoje. Use 'comi [alimento]' para registrar.")

    elif intent == 'limpar_refeicoes_dia':
        deleted_count = delete_all_food_entries_for_day(from_number)
        if deleted_count > 0:
            msg.body(f"Todas as {deleted_count} refeições de hoje foram excluídas com sucesso!")
        else:
            msg.body("Você não tem nenhuma refeição registrada hoje para excluir.")
    
    elif intent == 'excluir_refeicao_especifica':
        entry_number_list = entities.get('entry_number', [])
        
        if entry_number_list: 
            chosen_index = int(entry_number_list[0]) 
            
            current_meals = get_food_entries_for_day_indexed(from_number)
            meal_ids_map = { (i+1): meal['id'] for i, meal in enumerate(current_meals) }
            
            if meal_ids_map and chosen_index in meal_ids_map:
                meal_id_to_delete = meal_ids_map[chosen_index]
                deleted_rows = delete_food_entry_by_id(meal_id_to_delete)
                
                if deleted_rows > 0:
                    msg.body(f"Refeição número {chosen_index} excluída com sucesso!")
                else:
                    msg.body("Não foi possível excluir a refeição. Tente novamente.")
            else:
                msg.body("Número de refeição inválido. Por favor, digite um número que esteja na sua lista de refeições do dia.")
            
            set_user_state(from_number, 'none')
            return str(resp) 
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
                if 'T' in wit_time_obj and ':' in wit_time_obj: 
                    time_part = wit_time_obj.split('T')[1].split(':')[0:2] 
                    reminder_time_str = ":".join(time_part)
                elif re.match(r'^\d{2}:\d{2}$', wit_time_obj): 
                     reminder_time_str = wit_time_obj
                else: 
                    dt_object = datetime.fromisoformat(wit_time_obj.replace('Z', '+00:00')) 
                    reminder_time_str = dt_object.strftime('%H:%M')

            except Exception as e: 
                print(f"Erro ao parsear wit_time_obj '{wit_time_obj}': {e}")
                if re.match(r'^\d{2}:\d{2}$', wit_time_obj):
                    reminder_time_str = wit_time_obj


        if reminder_text and reminder_time_str:
            if add_reminder(from_number, reminder_text, reminder_time_str):
                scheduler.remove_all_jobs()
                scheduler.add_job(
                    send_good_morning_message,
                    CronTrigger(hour=8, minute=0),
                    id='daily_good_morning',
                    replace_existing=True
                )
                with app.app_context():
                    schedule_all_reminders()
                msg.body(f"Lembrete '{reminder_text}' às {reminder_time_str} desativado com sucesso.")
            else:
                msg.body("Não consegui definir o lembrete. Verifique o formato da hora (HH:MM).")
        else:
            msg.body("Não consegui identificar o texto ou a hora do lembrete. Use 'Definir lembrete [texto] [HH:MM]' (ex: 'Definir lembrete beber agua 10:00').")

    elif intent == 'listar_lembretes': 
        reminders = get_user_reminders(from_number)
        if reminders:
            response_lines = ["Seus lembretes ativos:"]
            for r in reminders:
                response_lines.append(f"- '{r['reminder_text']}' às {r['reminder_time']}")
            response_lines.append("\nPara desativar um, diga 'Desativar lembrete [texto] [HH:MM]'.")
            msg.body("\n".join(response_lines))
        else:
            msg.body("Você não tem lembretes ativos. Use 'definir lembrete' para criar um.")

    elif intent == 'desativar_lembrete': 
        reminder_text_list = entities.get('reminder_text', [])
        wit_time_obj = entities.get('wit_time')
        
        reminder_text = reminder_text_list[0] if reminder_text_list else None
        
        reminder_time_str = None
        if wit_time_obj:
            try:
                if 'T' in wit_time_obj and ':' in wit_time_obj:
                    time_part = wit_time_obj.split('T')[1].split(':')[0:2]
                    reminder_time_str = ":".join(time_part)
                elif re.match(r'^\d{2}:\d{2}$', wit_time_obj):
                     reminder_time_str = wit_time_obj
                else:
                    dt_object = datetime.fromisoformat(wit_time_obj.replace('Z', '+00:00'))
                    reminder_time_str = dt_object.strftime('%H:%M')
            except Exception as e:
                print(f"Erro ao parsear wit_time_obj '{wit_time_obj}': {e}")
                if re.match(r'^\d{2}:\d{2}$', wit_time_obj):
                    reminder_time_str = wit_time_obj

        if reminder_text and reminder_time_str:
            if deactivate_reminder(from_number, reminder_text, reminder_time_str):
                scheduler.remove_all_jobs()
                scheduler.add_job(
                    send_good_morning_message,
                    CronTrigger(hour=8, minute=0),
                    id='daily_good_morning',
                    replace_existing=True
                )
                with app.app_context():
                    schedule_all_reminders()
                msg.body(f"Lembrete '{reminder_text}' às {reminder_time_str} desativado com sucesso.")
            else:
                msg.body("Não encontrei esse lembrete para desativar. Verifique o texto e a hora.")
        else:
            msg.body("Não consegui identificar o texto ou a hora do lembrete a desativar. Use 'Desativar lembrete [texto] [HH:MM]'.")

    elif intent == 'saudacao': 
        msg.body("Olá! Eu sou seu assistente de saúde. Como posso te ajudar hoje?")

    else: # Intenção não reconhecida
        msg.body("Desculpe, não entendi o que você quis dizer. Por favor, tente de outra forma ou use um dos comandos: registrar peso, comi, fiz exercicio, resumo diario, minhas refeicoes, definir meta, definir lembrete, meus lembretes.")

    return str(resp)

if __name__ == "__main__":
    print("6. Tentando rodar o aplicativo Flask.") 
    app.run(debug=False, host='0.0.0.0', port=os.environ.get('PORT', 5000))
    print("7. Aplicativo Flask rodando (se você viu a mensagem de running, não verá esta).") 