# app.py
from flask import Flask, request
from twilio.twiml.messaging_response import MessagingResponse
from twilio.rest import Client
import os
from dotenv import load_dotenv
import re
from datetime import datetime, date

print("1. Imports carregados.") 

# Importa as funções que criaremos
from database import init_db, add_food_entry, add_weight_entry, add_exercise_entry, get_daily_summary, \
                     set_goal, get_goal, add_reminder, get_active_reminders, get_user_reminders, deactivate_reminder, \
                     update_last_interaction_date, get_last_interaction_date, get_all_users
from nutrition_api import get_nutrition_info
from activity_api import calculate_calories_burned

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
# Note: The CronTrigger (hour=8, minute=0) uses the timezone of the server running the script.
# If your server is in a different timezone than your users, you might need to adjust this or
# configure the scheduler with a specific timezone (e.g., scheduler = BackgroundScheduler(timezone='America/Sao_Paulo')).
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
    incoming_msg = request.values.get('Body', '').lower()
    from_number = request.values.get('From', '') # Número do usuário (whatsapp:+XXXXXXXX)

    resp = MessagingResponse()
    msg = resp.message()

    print(f"Mensagem recebida de {from_number}: {incoming_msg}")

    # --- ATUALIZA A DATA DA ÚLTIMA INTERAÇÃO A CADA MENSAGEM RECEBIDA ---
    with app.app_context():
        update_last_interaction_date(from_number)

    # --- Lógica de Processamento da Mensagem ---

    if "registrar peso" in incoming_msg:
        match = re.search(r'registrar peso (\d+(\.\d+)?)', incoming_msg)
        if match:
            try:
                weight = float(match.group(1))
                add_weight_entry(from_number, weight)
                msg.body(f"Peso de {weight} kg registrado com sucesso!")
            except ValueError:
                msg.body("Formato de peso inválido. Use 'registrar peso [valor]' (ex: 'registrar peso 75.5').")
        else:
            msg.body("Para registrar seu peso, digite 'registrar peso [valor]' (ex: 'registrar peso 75.5').")

    elif "comi" in incoming_msg or "consumi" in incoming_msg:
        food_query = ""
        if "comi " in incoming_msg:
            food_query = incoming_msg.split("comi ", 1)[1].strip()
        elif "consumi " in incoming_msg:
            food_query = incoming_msg.split("consumi ", 1)[1].strip()

        if food_query:
            nutrition_data = get_nutrition_info(food_query)
            if nutrition_data:
                total_calories = nutrition_data['calories']
                foods_listed = nutrition_data['foods_listed']
                add_food_entry(from_number, foods_listed, total_calories)

                calorie_goal = get_goal(from_number, 'calorie_intake')
                summary = get_daily_summary(from_number)
                total_consumed_today = sum(f[1] for f in summary['foods'])

                if calorie_goal and total_consumed_today > calorie_goal['target_value']:
                    msg.body(f"Registrado: {foods_listed} (aprox. {total_calories:.2f} calorias).\n"
                             f"🚨 Atenção: Você já consumiu {total_consumed_today:.2f} kcal, que excede sua meta diária de {calorie_goal['target_value']:.0f} kcal.")
                else:
                    msg.body(f"Registrado: {foods_listed} (aprox. {total_calories:.2f} calorias).")
            else:
                msg.body(f"Não consegui encontrar informações nutricionais para '{food_query}'. Tente ser mais específico ou digitar um por um.")
        else:
            msg.body("Para registrar o que você comeu, digite 'comi [alimento]' (ex: 'comi arroz e feijão').")

    elif "fiz exercicio" in incoming_msg or "treinei" in incoming_msg:
        match_exercise = re.search(r'(fiz exercicio|treinei)\s+([a-zA-Z\s]+?)\s+por\s+(\d+)\s*(minutos|min|horas|hr)', incoming_msg)
        if match_exercise:
            activity_name = match_exercise.group(2).strip()
            duration_value = int(match_exercise.group(3))
            duration_unit = match_exercise.group(4).lower()

            if duration_unit in ['horas', 'hr']:
                duration_minutes = duration_value * 60
            else:
                duration_minutes = duration_value

            summary_for_weight = get_daily_summary(from_number)
            user_weight_kg = summary_for_weight['last_weight'] if summary_for_weight['last_weight'] else 70

            calories_burned = calculate_calories_burned(activity_name, duration_minutes, user_weight_kg)

            if calories_burned > 0:
                add_exercise_entry(from_number, activity_name, duration_minutes, calories_burned)
                msg.body(f"Registrado: {activity_name} por {duration_value} {duration_unit}. Calorias queimadas estimadas: {calories_burned:.2f}.")
            else:
                msg.body(f"Não consegui estimar as calorias para '{activity_name}'. Tente um exercício mais comum.")
        else:
            msg.body("Para registrar um exercício, use 'fiz exercicio [nome] por [tempo]' (ex: 'fiz exercicio corrida por 30 minutos').")

    elif "minhas refeicoes" in incoming_msg or "minhas refeições" in incoming_msg:
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

    elif "resumo diario" in incoming_msg or "o que comi hoje" in incoming_msg:
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

    elif "definir meta" in incoming_msg:
        match_calorie_goal = re.search(r'definir meta calorias (\d+)', incoming_msg)
        match_weight_goal = re.search(r'definir meta peso (\d+(\.\d+)?)', incoming_msg)
        match_exercise_goal = re.search(r'definir meta exercicio (\d+)\s*vezes', incoming_msg)

        if match_calorie_goal:
            target_kcal = int(match_calorie_goal.group(1))
            set_goal(from_number, 'calorie_intake', target_kcal)
            msg.body(f"Meta de consumo diário de calorias definida para {target_kcal} kcal.")
        elif match_weight_goal:
            target_weight = float(match_weight_goal.group(1))
            set_goal(from_number, 'weight_loss', target_weight)
            msg.body(f"Meta de peso definida para {target_weight} kg.")
        elif match_exercise_goal:
            target_frequency = int(match_exercise_goal.group(1))
            set_goal(from_number, 'exercise_frequency', target_frequency)
            msg.body(f"Meta de exercícios definida para {target_frequency} vezes por semana.")
        else:
            msg.body("Formato inválido. Use 'definir meta calorias [valor]', 'definir meta peso [valor]' ou 'definir meta exercicio [numero] vezes'.")

    elif "minhas metas" in incoming_msg:
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

    elif "definir lembrete" in incoming_msg:
        match_reminder = re.search(r'definir lembrete (.+) (\d{2}:\d{2})', incoming_msg)
        if match_reminder:
            reminder_text = match_reminder.group(1).strip()
            reminder_time_str = match_reminder.group(2)
            
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
                msg.body(f"Lembrete '{reminder_text}' definido para as {reminder_time_str} com sucesso!.")
            else:
                msg.body("Não consegui definir o lembrete. Verifique o formato da hora (HH:MM).")
        else:
            msg.body("Formato inválido. Use 'definir lembrete [texto do lembrete] [HH:MM]' (ex: 'definir lembrete beber agua 10:00').")

    elif "meus lembretes" in incoming_msg:
        reminders = get_user_reminders(from_number)
        if reminders:
            response_lines = ["Seus lembretes ativos:"]
            for r in reminders:
                response_lines.append(f"- '{r['reminder_text']}' às {r['reminder_time']}")
            response_lines.append("\nPara desativar um, diga 'desativar lembrete [texto] [HH:MM]'.")
            msg.body("\n".join(response_lines))
        else:
            msg.body("Você não tem lembretes ativos. Use 'definir lembrete' para criar um.")

    elif "desativar lembrete" in incoming_msg:
        match_deactivate = re.search(r'desativar lembrete (.+) (\d{2}:\d{2})', incoming_msg)
        if match_deactivate:
            reminder_text = match_deactivate.group(1).strip()
            reminder_time_str = match_deactivate.group(2)
            
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
            msg.body("Formato inválido. Use 'desativar lembrete [texto do lembrete] [HH:MM]'.")


    elif "olá" in incoming_msg or "oi" in incoming_msg:
        msg.body("Olá! Eu sou seu assistente de saúde. Você pode me dizer 'registrar peso [valor]', 'comi [alimentos]', 'fiz exercicio [nome] por [tempo]', 'resumo diario', 'minhas refeicoes', 'definir meta', 'definir lembrete' ou 'meus lembretes'.")

    else:
        msg.body("Desculpe, não entendi. Tente 'registrar peso', 'comi', 'fiz exercicio', 'resumo diario', 'minhas refeicoes', 'definir meta', 'definir lembrete' ou 'meus lembretes'.")

    return str(resp)

if __name__ == "__main__":
    print("6. Tentando rodar o aplicativo Flask.") 
    # Mantenha a porta 5000, ou mude para 5001 se ainda tiver conflitos,
    # mas lembre-se de atualizar o Serveo.net e o Twilio também!
    app.run(debug=True, host='0.0.0.0', port=5000) # Usando uma porta bem alta e incomum
    print("7. Aplicativo Flask rodando (se você viu a mensagem de running, não verá esta).")

    import os
