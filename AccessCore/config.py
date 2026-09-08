# config.py
import urllib.parse

# --- CONFIGURE SEU ACESSO AO SQL SERVER AQUI ---

# Adicionamos um 'r' antes das aspas para corrigir o SyntaxWarning (da barra '\A')
DB_SERVER = r"localhost\ACCESSCORE"  # <<< ALTERAÇÃO AQUI
DB_NAME = "AccessCoreDB"
DB_USERNAME = "sa"
DB_PASSWORD = "*rfg2025*"
DB_DRIVER = "ODBC Driver 18 for SQL Server"
# -------------------------------------------------

# Codifica a senha para caso ela tenha caracteres especiais (ex: @, #, !)
params = urllib.parse.quote_plus(
    f"DRIVER={{{DB_DRIVER}}};"
    f"SERVER={DB_SERVER};"
    f"DATABASE={DB_NAME};"
    f"UID={DB_USERNAME};"
    f"PWD={DB_PASSWORD};"
    "MARS_Connection=yes;"
    "TrustServerCertificate=yes;"  # <<< ADICIONE ESTA LINHA (A SOLUÇÃO)
)

# String de conexão principal que o SQLAlchemy usará
SQLALCHEMY_DATABASE_URI = f"mssql+pyodbc:///?odbc_connect={params}"
SQLALCHEMY_TRACK_MODIFICATIONS = False

# Chave secreta para sessões do Flask (necessário para login)
SECRET_KEY = "f5d1a8e2c9b3f7a0d6e8c4b7f1a9d0c5b6e3f2a1d0c9b8e7"