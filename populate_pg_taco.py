# populate_pg_taco.py
import csv
import psycopg2
from psycopg2 import sql 
import os
from dotenv import load_dotenv

print("DEBUG: populate_pg_taco.py - INICIO DO SCRIPT.") 
load_dotenv() 
print(f"DEBUG: populate_pg_taco.py - load_dotenv() executado. DATABASE_URL raw: {os.getenv('DATABASE_URL')}")

DATABASE_URL = os.getenv('DATABASE_URL')
if not DATABASE_URL:
    print("ERRO CRÍTICO: DATABASE_URL não está configurada no .env ou está vazia!") 
    raise ValueError("DATABASE_URL não está configurada no .env! Não é possível conectar ao PostgreSQL.")
else:
    print("DEBUG: DATABASE_URL parece estar configurada.") 

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
    """Importa dados do CSV da TACO para a tabela taco_foods no PostgreSQL."""
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

    total_imported_foods = 0 # Acumula o total de todos os CSVs
    
    with open(file_path, mode='r', encoding='utf-8') as file: # Loop removido, pois TACO_CSV_FILES é um só arquivo
        csv_reader = csv.DictReader(file)
        
        imported_count_this_file = 0 # Contador para este CSV específico
        skipped_count_this_file = 0 # Contador de pulados para este CSV
        
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

        for row_num, row in enumerate(csv_reader): 
            try:
                alimento = row.get('Descrição dos alimentos', '').strip()
                
                def safe_float_convert(value_str):
                    if not value_str: 
                        return 0.0
                    value_str = value_str.strip().replace(',', '.')
                    if value_str.lower() in ('na', 'nd'): 
                        return 0.0
                    try:
                        return float(value_str)
                    except ValueError: 
                        return 0.0
                
                energia_kcal = safe_float_convert(row.get('Energia..kcal.', '0'))
                proteina_g = safe_float_convert(row.get('Proteína..g.', '0'))
                lipidios_g = safe_float_convert(row.get('Lipídeos..g.', '0'))
                carboidrato_g = safe_float_convert(row.get('Carboidrato..g.', '0'))
                
            except Exception as e: 
                print(f"Aviso na linha {row_num + 2} (no CSV): Erro ao processar valores: {row}. Erro: {e}. Pulando linha.")
                skipped_count_this_file += 1
                continue

            cursor.execute("SELECT id FROM taco_foods WHERE alimento = %s", (alimento,)) 
            existing_food = cursor.fetchone()

            if not existing_food and alimento: 
                try:
                    cursor.execute(insert_query, {
                        'alimento': alimento,
                        'energia_kcal': energia_kcal,
                        'proteina_g': proteina_g,
                        'lipidios_g': lipidios_g,
                        'carboidrato_g': carboidrato_g
                    })
                    imported_count_this_file += 1
                except psycopg2.IntegrityError as e: 
                    print(f"Aviso na linha {row_num + 2}: Alimento '{alimento}' já existe (UNIQUE CONSTRAINT). Erro: {e}. Pulando.")
                    conn.rollback() 
                    skipped_count_this_file += 1
                except Exception as e:
                    print(f"ERRO DE INSERÇÃO na linha {row_num + 2}: Não foi possível inserir '{alimento}'. Erro: {e}. Linha: {row}. Pulando.")
                    conn.rollback() 
                    skipped_count_this_file += 1
            else: 
                skipped_count_this_file += 1
                if not alimento:
                    print(f"Aviso na linha {row_num + 2}: Alimento vazio. Pulando.")


    conn.commit() 
    total_imported_foods += imported_count_this_file # Acumula para o total final
    print(f"Importados {imported_count_this_file} alimentos do arquivo '{TACO_CSV_FILE}' para o PostgreSQL. ({skipped_count_this_file} pulados neste arquivo).")


    cursor.execute("SELECT COUNT(*) FROM taco_foods;")
    actual_row_count = cursor.fetchone()[0]
    print(f"Verificação FINAL: Total REAL de linhas na tabela 'taco_foods' no PostgreSQL é {actual_row_count}.")

    cursor.close()
    conn.close()
    print(f"População de dados da TACO no PostgreSQL concluída. Total de alimentos contados pelo script: {total_imported_foods}.")
    if skipped_count_this_file > 0:
        print(f"Aviso Geral: {skipped_count_this_file} linhas foram puladas devido a erros ou duplicatas.")

if __name__ == '__main__':
    populate_pg_taco_data()