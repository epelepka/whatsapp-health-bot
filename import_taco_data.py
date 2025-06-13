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
            # AJUSTADO COM BASE NOS SEUS CABEÇALHOS ATUAIS
            column_mapping = {
                'Descrição dos alimentos': 'alimento',
                'Energia..kcal.': 'energia_kcal',      # AJUSTADO AQUI
                'Proteína..g.': 'proteina_g',          # AJUSTADO AQUI
                'Lipídeos..g.': 'lipidios_g',          # AJUSTADO AQUI
                'Carboidrato..g.': 'carboidrato_g'      # AJUSTADO AQUI
            }
            
            # Verificar se todos os cabeçalhos esperados estão no CSV
            csv_headers = csv_reader.fieldnames
            missing_headers = [header for header in column_mapping.keys() if header not in csv_headers]
            if missing_headers:
                print(f"ERRO: Cabeçalhos obrigatórios ausentes no CSV '{csv_file}': {missing_headers}. Verifique os nomes das colunas e o arquivo TACO. Pulando este arquivo.")
                continue

            for row in csv_reader:
                # Converte os dados para float e trata valores ausentes/vazios/NAs
                # Substitui vírgulas por pontos para números decimais
                try:
                    alimento = row.get('Descrição dos alimentos', '').strip()
                    
                    energia_kcal_str = row.get('Energia..kcal.', 'NA').replace(',', '.')
                    proteina_g_str = row.get('Proteína..g.', 'NA').replace(',', '.')
                    lipidios_g_str = row.get('Lipídeos..g.', 'NA').replace(',', '.')
                    carboidrato_g_str = row.get('Carboidrato..g.', 'NA').replace(',', '.')

                    # Trata "NA" e converte para float
                    energia_kcal = float(energia_kcal_str) if energia_kcal_str not in ('NA', '') else 0.0
                    proteina_g = float(proteina_g_str) if proteina_g_str not in ('NA', '') else 0.0
                    lipidios_g = float(lipidios_g_str) if lipidios_g_str not in ('NA', '') else 0.0
                    carboidrato_g = float(carboidrato_g_str) if carboidrato_g_str not in ('NA', '') else 0.0
                    
                except ValueError as e:
                    print(f"Aviso: Erro ao converter dados numéricos da linha: {row}. Erro: {e}. Pulando linha.")
                    continue
                except KeyError as e:
                    print(f"ERRO: Coluna '{e}' não encontrada no CSV '{csv_file}'. Verifique os cabeçalhos. Pulando arquivo.")
                    break # Sai deste CSV e tenta o próximo

                # Verifica se o alimento já existe (para evitar duplicatas se o CSV tiver)
                cursor.execute("SELECT id FROM taco_foods WHERE alimento = ?", (alimento,))
                existing_food = cursor.fetchone()

                if not existing_food and alimento: # Só insere se não existir e o nome do alimento não for vazio
                    try:
                        cursor.execute(
                            "INSERT INTO taco_foods (alimento, energia_kcal, proteina_g, lipidios_g, carboidrato_g) VALUES (?, ?, ?, ?, ?)",
                            (alimento, energia_kcal, proteina_g, lipidios_g, carboidrato_g)
                        )
                        imported_count += 1
                    except sqlite3.IntegrityError:
                        print(f"Aviso: Alimento '{alimento}' já existe (problema de UNIQUE). Pulando.")
                
            conn.commit()
            total_imported_foods += imported_count
            print(f"Importados {imported_count} alimentos do arquivo '{csv_file}'.")

    conn.close()
    print(f"Importação de dados da TACO concluída. Total de alimentos importados: {total_imported_foods}.")

if __name__ == '__main__':
    # Importa init_db para garantir que a tabela taco_foods exista antes de importar
    from database import init_db
    init_db() 
    
    import_taco_data()