# config.py
import os
import urllib.parse
from dotenv import load_dotenv

# Carrega as variáveis definidas no arquivo .env (que NÃO vai para o Git)
load_dotenv()

# --- CONFIGURAÇÃO DE ACESSO AO SQL SERVER (lida do .env) ---
DB_SERVER = os.environ.get("DB_SERVER")
DB_NAME = os.environ.get("DB_NAME")
DB_USERNAME = os.environ.get("DB_USERNAME")
DB_PASSWORD = os.environ.get("DB_PASSWORD")
DB_DRIVER = os.environ.get("DB_DRIVER", "ODBC Driver 18 for SQL Server")
# -------------------------------------------------------------

# Codifica a senha para caso ela tenha caracteres especiais (ex: @, #, !)
params = urllib.parse.quote_plus(
    f"DRIVER={{{DB_DRIVER}}};"
    f"SERVER={DB_SERVER};"
    f"DATABASE={DB_NAME};"
    f"UID={DB_USERNAME};"
    f"PWD={DB_PASSWORD};"
    "MARS_Connection=yes;"
    "TrustServerCertificate=yes;"
)

# String de conexão principal que o SQLAlchemy usará
SQLALCHEMY_DATABASE_URI = f"mssql+pyodbc:///?odbc_connect={params}"
SQLALCHEMY_TRACK_MODIFICATIONS = False

# Chave secreta para sessões do Flask (lida do .env)
SECRET_KEY = os.environ.get("SECRET_KEY")
