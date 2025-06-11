# app.py
from flask import Flask, request
from twilio.twiml.messaging_response import MessagingResponse
from twilio.rest import Client
import os
from dotenv import load_dotenv
import re
from datetime import datetime, date, time # Import time for datetime.fromisoformat

print("1. Imports carregados.") 

# Importa as funções que criaremos
from database import init_db, add_food_entry, add_weight_entry, add_exercise_entry, get_daily_summary, \
                     set_goal, get_goal, add_reminder, get_active_reminders, get_user_reminders, deactivate_reminder, \
                     update_last_interaction_date, get_last_interaction_date, get_all_users
from nutrition_api import get_nutrition_info
from activity_api import calculate_calories_burned
from wit_nlp import get_wit_ai_response, parse_wit_ai_response # NOVO: Importa as funções do wit_nlp

print("2. Funções do banco de dados e APIs importadas.") 

# Para agendamento de tarefas
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
import atexit # Para garantir que o agendador seja desligado corretamente

load_dotenv() # Carrega as variáveis de ambiente do arquivo .env

app = Flask(__name__)

print("3. Flask app criado.") 

# Configurações da Twilio (do .env)
TWILIO_ACCOUNT_SID = os.getenv('TWILIO_ACCOUNT_SID')
TWILIO_AUTH_TOKEN = os.getenv('TWILIO_AUTH_TOKEN')
TWILIO_WHATSAPP_NUMBER = os.getenv('TWILIO_WHATSAPP_NUMBER') # Seu número Twilio WhatsApp habilitado

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
    incoming_msg = request.values.get('Body', '') # Removido .lower() aqui para o Wit.ai processar melhor
    from_number = request.values.get('From', '') # Número do usuário (whatsapp:+XXXXXXXX)

    resp = MessagingResponse()
    msg = resp.message()

    print(f"Mensagem recebida de {from_number}: {incoming_msg}")

    # --- ATUALIZA A DATA DA ÚLTIMA INTERAÇÃO A CADA MENSAGEM RECEBIDA ---
    with app.app_context():
        update_last_interaction_date(from_number)

    # --- NOVO: Processar a mensagem com Wit.ai ---
    wit_response = get_wit_ai_response(incoming_msg) # Envia a mensagem original (não .lower())
    parsed_data = parse_wit_ai_response(wit_response)
    
    intent = parsed_data['intent']
    entities = parsed_data['entities']

    print(f"Intenção detectada: {intent}, Entidades: {entities}")

    # --- Lógica baseada na Intenção detectada ---

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
        food_query = entities.get('food_item') 
        if food_query:
            # Se food_item pode ser uma lista, converta para string para a API
            if isinstance(food_query, list):
                food_query = ", ".join(food_query)
            
            # Garante que o food_query seja uma string antes de passar para a API
            food_query_str = str(food_query)

            nutrition_data = get_nutrition_info(food_query_str)
            if nutrition_data:
                total_calories = nutrition_data['calories']
                foods_listed = nutrition_data['foods_listed']
                add_food_entry(from_number, foods_listed, total_calories)

                calorie_goal = get_goal(from_number, 'calorie_intake')
                summary = get_daily_summary(from_number)
                total_consumed_today = sum(f[1] for f in summary['foods'])

                response_text = f"Registrado: {foods_listed} (aprox. {total_calories:.2f} calorias)."
                if calorie_goal and total_consumed_today > calorie_goal['target_value']:
                    response_text += (f"\n🚨 Atenção: Você já consumiu {total_consumed_today:.2f} kcal, "
                                      f"que excede sua meta diária de {calorie_goal['target_value']:.0f} kcal.")
                msg.body(response_text)
            else:
                msg.body(f"Não consegui encontrar informações nutricionais para '{food_query_str}'. Tente ser mais específico.")
        else:
            msg.body("Não consegui identificar o que você comeu. Por favor, diga (ex: 'Comi arroz e frango').")

    elif intent == 'registrar_exercicio':
        activity_name = entities.get('activity_name')
        duration_value = entities.get('duration_value')
        duration_unit = entities.get('duration_unit')

        if activity_name and duration_value and duration_unit:
            try:
                duration_minutes = int(duration_value)
                if duration_unit.lower() in ['horas', 'hr', 'hora']: # Adicionado 'hora'
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
            food_summary = "\n".join([f"- {f[0]} ({f[1]:.2f} kcal)" for f in summary['foods']])
            exercise_summary = "\n".join([f"- {e[0]} por {e[1]} min ({e[2]:.2f} kcal) queimadas" for e in summary['exercises']])
            weight_info = f"Seu último peso registrado: {summary['last_weight']:.1f} kg" if summary['last_weight'] else "Nenhum peso registrado."
            total_calories_consumed = sum(f[1] for f in summary['foods'])
            total_calories_burned = sum(e[2] for e in summary['exercises'])

            response_text = (
                f"Resumo do dia para {from_number}:\n\n"
                f"--- Alimentação ({total_calories_consumed:.2f} kcal) ---\n"
                f"{food_summary if food_summary else 'Nenhum alimento registrado.'}\n\n"
                f"--- Exercícios ({total_calories_burned:.2f} kcal queimadas) ---\n"
                f"{exercise_summary if exercise_summary else 'Nenhum exercício registrado.'}\n\n"
                f"{weight_info}\n\n"
                f"Balanço calórico estimado: {total_calories_consumed - total_calories_burned:.2f} kcal (Calorias Consumidas - Calorias Queimadas)"
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
                food_description = food_entry[0]
                calories = food_entry[1]
                response_lines.append(f"- {food_description} ({calories:.2f} kcal)")
                total_calories_consumed += calories
            response_lines.append(f"\nTotal de calorias consumidas hoje: {total_calories_consumed:.2f} kcal.")
            msg.body("\n".join(response_lines))
        else:
            msg.body("Você ainda não registrou nenhuma refeição hoje. Use 'comi [alimento]' para registrar.")

    elif intent == 'definir_meta':
        goal_type = entities.get('goal_type')
        target_value = entities.get('target_value')
        
        if goal_type and target_value:
            try:
                target_value = float(target_value) # Sempre float para valores de meta
                set_goal(from_number, goal_type, target_value)
                msg.body(f"Meta de {goal_type} definida para {target_value} com sucesso!")
            except ValueError:
                msg.body("Formato de valor para meta inválido. Por favor, use um número.")
        else:
            msg.body("Não consegui definir a meta. Use 'Definir meta [tipo] [valor]' (ex: 'Definir meta calorias 2000').")

    elif intent == 'listar_metas': # Adicionado intenção para "minhas metas"
        calorie_goal = get_goal(from_number, 'calorie_intake')
        weight_goal = get_goal(from_number, 'weight_loss')
        exercise_goal = get_goal(from_number, 'exercise_frequency')

        response_lines = ["Suas Metas:"]
        if calorie_goal:
            response_lines.append(f"- Consumo diário de calorias: {calorie_goal['target_value']:.0f} kcal")
        if weight_goal:
            response_lines.append(f"- Peso Alvo: {weight_goal['target_value']:.1f} kg")
        if exercise_goal:
            response_lines.append(f"- Frequência de Exercícios: {exercise_goal['target_value']:.0f} vezes por semana")

        if len(response_lines) == 1:
            response_lines.append("Você ainda não definiu nenhuma meta. Use 'definir meta [tipo] [valor]'.")

        if weight_goal:
            summary = get_daily_summary(from_number)
            current_weight = summary['last_weight']
            if current_weight:
                if current_weight <= weight_goal['target_value']:
                    response_lines.append(f"🎉 Parabéns! Você atingiu ou superou sua meta de peso de {weight_goal['target_value']:.1f} kg!")
                else:
                    diff = current_weight - weight_goal['target_value']
                    response_lines.append(f"Seu peso atual é {current_weight:.1f} kg. Faltam {diff:.1f} kg para sua meta de {weight_goal['target_value']:.1f} kg.")

        msg.body("\n".join(response_lines))

    elif intent == 'definir_lembrete':
        reminder_text = entities.get('reminder_text')
        wit_time_obj = entities.get('wit_time') # O wit.ai retorna a hora aqui
        
        # O wit.ai retorna a hora no formato ISO 8601. Precisamos extrair HH:MM
        reminder_time_str = None
        if wit_time_obj:
            try:
                # dt_object = datetime.fromisoformat(wit_time_obj)
                # Para evitar problemas de fuso horário, pegue apenas a parte da hora
                # Exemplo: '2025-06-11T10:00:00.000-03:00'
                # Ou se for apenas uma string de tempo como '10:00'
                if 'T' in wit_time_obj and ':' in wit_time_obj: # Parece um formato ISO
                    time_part = wit_time_obj.split('T')[1].split(':')[0:2] # Pega HH:MM
                    reminder_time_str = ":".join(time_part)
                elif re.match(r'^\d{2}:\d{2}$', wit_time_obj): # Se já for HH:MM
                     reminder_time_str = wit_time_obj
                else: # Último recurso, tenta parsear como datetime e formatar
                    dt_object = datetime.fromisoformat(wit_time_obj.replace('Z', '+00:00')) # Handle UTC 'Z'
                    reminder_time_str = dt_object.strftime('%H:%M')

            except Exception as e: # Captura exceções mais genéricas de parsing
                print(f"Erro ao parsear wit_time_obj '{wit_time_obj}': {e}")


        if reminder_text and reminder_time_str:
            if add_reminder(from_number, reminder_text, reminder_time_str):
                # O agendador precisa ser reconfigurado após adicionar/desativar lembretes
                scheduler.remove_all_jobs()
                scheduler.add_job(
                    send_good_morning_message,
                    CronTrigger(hour=8, minute=0),
                    id='daily_good_morning',
                    replace_existing=True
                )
                with app.app_context():
                    schedule_all_reminders()
                msg.body(f"Lembrete '{reminder_text}' definido para as {reminder_time_str} com sucesso!")
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
            msg.body("Você não tem lembretes ativos. Use 'Definir lembrete' para criar um.")

    elif intent == 'desativar_lembrete': 
        reminder_text = entities.get('reminder_text')
        wit_time_obj = entities.get('wit_time')
        
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
    # Em produção, a porta é definida pelo ambiente (Railway faz isso).
    # Em desenvolvimento, você pode fixar a porta.
    # Certifique-se que o host é '0.0.0.0' para ser acessível externamente (pelo Railway).
    app.run(debug=False, host='0.0.0.0', port=os.environ.get('PORT', 5000)) # Use os.environ.get('PORT', 5000) para Railway
    print("7. Aplicativo Flask rodando (se você viu a mensagem de running, não verá esta).") 