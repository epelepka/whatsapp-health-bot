# populate_pg_taco.py
import csv
import psycopg2
import os
from dotenv import load_dotenv

print("DEBUG: populate_pg_taco.py - INICIO DO SCRIPT.") # DEBUG AQUI
load_dotenv() 
print(f"DEBUG: populate_pg_taco.py - load_dotenv() executado. DATABASE_URL raw: {os.getenv('DATABASE_URL')}") # DEBUG AQUI

DATABASE_URL = os.getenv('DATABASE_URL')
if not DATABASE_URL:
    print("ERRO CRÍTICO: DATABASE_URL não está configurada no .env ou está vazia!") # DEBUG AQUI
    raise ValueError("DATABASE_URL não está configurada no .env! Não é possível conectar ao PostgreSQL.")
else:
    print("DEBUG: DATABASE_URL parece estar configurada.") # DEBUG AQUI

TACO_CSV_FILE = 'taco_data.csv' 

def get_pg_connection():
    print("DEBUG: Tentando conectar ao PostgreSQL...")
    try:
        conn = psycopg2.connect(DATABASE_URL + "?sslmode=require")
        print("DEBUG: Conexão com PostgreSQL estabelecida.")
        return conn
    except Exception as e:
        print(f"ERRO CRÍTICO: Falha ao conectar ao PostgreSQL: {e}")
        raise 

def populate_pg_taco_data():
    conn = get_pg_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute("TRUNCATE TABLE taco_foods RESTART IDENTITY;") 
        conn.commit()
        print("Tabela 'taco_foods' limpa para nova importação no PostgreSQL.")
    except Exception as e:
        print(f"ERRO: Falha ao limpar tabela 'taco_foods': {e}. Verifique as permissões do DB ou se a tabela existe.")
        conn.close()
        return


    file_path = os.path.join(os.getcwd(), TACO_CSV_FILE)
    
    if not os.path.exists(file_path):
        print(f"ERRO: Arquivo '{TACO_CSV_FILE}' não encontrado em '{file_path}'. Certifique-se que está na pasta do projeto.")
        conn.close()
        return

    imported_count = 0
    with open(file_path, mode='r', encoding='utf-8') as file:
        csv_reader = csv.DictReader(file)
        
        column_mapping = {
            'Descrição dos alimentos': 'alimento',
            'Energia..kcal.': 'energia_kcal',
            'Proteína..g.': 'proteina_g',
            'Lipídeos..g.': 'lipidios_g',
            'Carboidrato..g.': 'carboidrato_g'
        }
        
        csv_headers = csv_reader.fieldnames
        missing_headers = [header for header in column_mapping.keys() if header not in csv_headers]
        if missing_headers:
            print(f"ERRO: Cabeçalhos obrigatórios ausentes no CSV '{TACO_CSV_FILE}': {missing_headers}. Verifique os nomes das colunas e o arquivo TACO.")
            conn.close()
            return

        insert_query = sql.SQL("INSERT INTO taco_foods (alimento, energia_kcal, proteina_g, lipidios_g, carboidrato_g) VALUES ({}, {}, {}, {}, {})").format(
            sql.Placeholder('alimento'), sql.Placeholder('energia_kcal'), sql.Placeholder('proteina_g'),
            sql.Placeholder('lipidios_g'), sql.Placeholder('carboidrato_g')
        )

        for row in csv_reader:
            try:
                alimento = row.get('Descrição dos alimentos', '').strip()
                energia_kcal = float(row.get('Energia..kcal.', '0').replace(',', '.'))
                proteina_g = float(row.get('Proteína..g.', '0').replace(',', '.'))
                lipidios_g = float(row.get('Lipídeos..g.', '0').replace(',', '.'))
                carboidrato_g = float(row.get('Carboidrato..g.', '0').replace(',', '.'))
                
                cursor.execute(insert_query, {
                    'alimento': alimento,
                    'energia_kcal': energia_kcal,
                    'proteina_g': proteina_g,
                    'lipidios_g': lipidios_g,
                    'carboidrato_g': carboidrato_g
                })
                imported_count += 1
            except ValueError as e:
                print(f"Aviso: Erro ao converter dados numéricos da linha: {row}. Erro: {e}. Pulando linha.")
                conn.rollback() 
                continue
            except psycopg2.IntegrityError:
                print(f"Aviso: Alimento '{alimento}' já existe (problema de UNIQUE). Pulando.")
                conn.rollback() 
            except Exception as e:
                print(f"ERRO DE INSERÇÃO: Não foi possível inserir '{alimento}'. Erro: {e}. Linha: {row}. Pulando.")
                conn.rollback() 
                
        conn.commit() 
        print(f"Importados {imported_count} alimentos para o PostgreSQL.")

    cursor.execute("SELECT COUNT(*) FROM taco_foods;")
    actual_row_count = cursor.fetchone()[0]
    print(f"Verificação: Total REAL de linhas na tabela 'taco_foods' no PostgreSQL é {actual_row_count}.")

    cursor.close()
    conn.close()
    print(f"População de dados da TACO no PostgreSQL concluída. Total de alimentos contados pelo script: {imported_count}.")

if __name__ == '__main__':
    populate_pg_taco_data()