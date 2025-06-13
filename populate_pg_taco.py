# populate_pg_taco.py
import csv
import psycopg2
import os
from dotenv import load_dotenv

load_dotenv() # Carrega DATABASE_URL do .env

# URL de conexão com o PostgreSQL do Railway (copie do painel do Railway, seção Connect)
DATABASE_URL = os.getenv('DATABASE_URL')
if not DATABASE_URL:
    raise ValueError("DATABASE_URL não está configurada no .env! Não é possível conectar ao PostgreSQL.")

# Nome do arquivo CSV da TACO
# AJUSTE ESTE NOME SE O SEU ARQUIVO TIVER NOME DIFERENTE
TACO_CSV_FILE = 'taco_data.csv' 

def get_pg_connection():
    """Retorna uma conexão com o banco de dados PostgreSQL."""
    return psycopg2.connect(DATABASE_URL + "?sslmode=require")

def populate_pg_taco_data():
    """Importa dados do CSV da TACO para a tabela taco_foods no PostgreSQL."""
    conn = get_pg_connection()
    cursor = conn.cursor()

    # Limpa a tabela taco_foods antes de importar para evitar duplicatas
    cursor.execute("TRUNCATE TABLE taco_foods RESTART IDENTITY;") # TRUNCATE para limpar e resetar IDs
    conn.commit()
    print("Tabela 'taco_foods' limpa para nova importação no PostgreSQL.")

    file_path = os.path.join(os.getcwd(), TACO_CSV_FILE)

    if not os.path.exists(file_path):
        print(f"ERRO: Arquivo '{TACO_CSV_FILE}' não encontrado em '{file_path}'. Certifique-se que está na pasta do projeto.")
        conn.close()
        return

    with open(file_path, mode='r', encoding='utf-8') as file:
        csv_reader = csv.DictReader(file)
        imported_count = 0

        # Mapeamento de colunas do CSV para as colunas do DB
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

        # Prepara a query de inserção
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

                # Insere no PostgreSQL
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
                conn.rollback() # Desfaz a transação atual
                continue
            except psycopg2.IntegrityError:
                print(f"Aviso: Alimento '{alimento}' já existe (problema de UNIQUE). Pulando.")
                conn.rollback() # Desfaz a transação atual
            except Exception as e:
                print(f"ERRO DE INSERÇÃO: Não foi possível inserir '{alimento}'. Erro: {e}. Linha: {row}. Pulando.")
                conn.rollback() # Desfaz a transação atual

        conn.commit() # Confirma todas as inserções
        print(f"Importados {imported_count} alimentos para o PostgreSQL.")

    cursor.execute("SELECT COUNT(*) FROM taco_foods;")
    actual_row_count = cursor.fetchone()[0]
    print(f"Verificação: Total REAL de linhas na tabela 'taco_foods' no PostgreSQL é {actual_row_count}.")

    cursor.close()
    conn.close()
    print(f"População de dados da TACO no PostgreSQL concluída. Total de alimentos contados pelo script: {imported_count}.")