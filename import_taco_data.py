# import_taco_data.py
import csv
import sqlite3
import os

# Define o nome do arquivo do banco de dados (o mesmo que no database.py)
DATABASE_FILE = 'health_assistant.db'

# AJUSTADO: Agora aponta para APENAS UM arquivo CSV
TACO_CSV_FILES = [
    'taco_data.csv' # Certifique-se que o arquivo CSV correto está com este nome
]

def get_db_connection():
    """Retorna uma conexão com o banco de dados SQLite."""
    conn = sqlite3.connect(DATABASE_FILE)
    conn.row_factory = sqlite3.Row # Para acessar colunas por nome
    return conn

def import_taco_data():
    """Importa dados dos CSVs da TACO para a tabela taco_foods."""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Limpa a tabela taco_foods antes de importar para evitar duplicatas
    # CUIDADO: Isso apaga todos os dados existentes na tabela taco_foods
    cursor.execute("DELETE FROM taco_foods")
    conn.commit()
    print("Tabela 'taco_foods' limpa para nova importação.")

    total_imported_foods = 0

    for csv_file in TACO_CSV_FILES:
        file_path = os.path.join(os.getcwd(), csv_file) # Constrói o caminho completo do arquivo
        
        if not os.path.exists(file_path):
            print(f"ERRO: Arquivo '{csv_file}' não encontrado em '{file_path}'. Pule este arquivo.")
            continue

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
            
            # Verificar se todos os cabeçalhos esperados estão no CSV
            csv_headers = csv_reader.fieldnames
            missing_headers = [header for header in column_mapping.keys() if header not in csv_headers]
            if missing_headers:
                print(f"ERRO: Cabeçalhos obrigatórios ausentes no CSV '{csv_file}': {missing_headers}. Verifique os nomes das colunas e o arquivo TACO. Pulando este arquivo.")
                continue

            for row in csv_reader:
                try:
                    alimento = row.get('Descrição dos alimentos', '').strip()
                    
                    energia_kcal_str = row.get('Energia..kcal.', 'NA').replace(',', '.')
                    proteina_g_str = row.get('Proteína..g.', 'NA').replace(',', '.')
                    lipidios_g_str = row.get('Lipídeos..g.', 'NA').replace(',', '.')
                    carboidrato_g_str = row.get('Carboidrato..g.', 'NA').replace(',', '.')

                    energia_kcal = float(energia_kcal_str) if energia_kcal_str not in ('NA', '') else 0.0
                    proteina_g = float(proteina_g_str) if proteina_g_str not in ('NA', '') else 0.0
                    lipidios_g = float(lipidios_g_str) if lipidios_g_str not in ('NA', '') else 0.0
                    carboidrato_g = float(carboidrato_g_str) if carboidrato_g_str not in ('NA', '') else 0.0
                    
                except ValueError as e:
                    print(f"Aviso: Erro ao converter dados numéricos da linha: {row}. Erro: {e}. Pulando linha.")
                    continue
                except KeyError as e:
                    print(f"ERRO: Coluna '{e}' não encontrada no CSV '{csv_file}'. Verifique os cabeçalhos. Pulando arquivo.")
                    break 

                cursor.execute("SELECT id FROM taco_foods WHERE alimento = ?", (alimento,))
                existing_food = cursor.fetchone()

                if not existing_food and alimento: 
                    try:
                        cursor.execute(
                            "INSERT INTO taco_foods (alimento, energia_kcal, proteina_g, lipidios_g, carboidrato_g) VALUES (?, ?, ?, ?, ?)",
                            (alimento, energia_kcal, proteina_g, lipidios_g, carboidrato_g)
                        )
                        # NOVO: Commit após cada inserção para garantir persistência imediata
                        conn.commit() 
                        imported_count += 1
                    except sqlite3.IntegrityError:
                        print(f"Aviso: Alimento '{alimento}' já existe (problema de UNIQUE). Pulando.")
                    except Exception as e: 
                        print(f"ERRO DE INSERÇÃO: Não foi possível inserir '{alimento}'. Erro: {e}. Linha: {row}. Pulando.")
                
            # Removido conn.commit() aqui para que o commit seja feito a cada linha acima.
            total_imported_foods += imported_count
            print(f"Importados {imported_count} alimentos do arquivo '{csv_file}'.")

    # --- NOVO: VERIFICAÇÃO FINAL DE CONTADOR DE LINHAS APÓS TODAS AS IMPORTAÇÕES ---
    cursor.execute("SELECT COUNT(*) FROM taco_foods")
    actual_row_count = cursor.fetchone()[0]
    print(f"Verificação FINAL: Total REAL de linhas na tabela 'taco_foods' é {actual_row_count}.")
    # --- FIM DA VERIFICAÇÃO ---

    conn.close() # A conexão é fechada apenas no final
    print(f"Importação de dados da TACO concluída. Total de alimentos contados pelo script: {total_imported_foods}.")

if __name__ == '__main__':
    from database import init_db
    init_db() 
    
    import_taco_data()