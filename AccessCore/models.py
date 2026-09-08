# models.py
from extensions import db
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash

# -------------------------------------------------------------------
# MODELOS DE CONFIGURAÇÃO E ACESSO
# -------------------------------------------------------------------

class Operador(db.Model):
    """
    Representa o usuário que opera o sistema (Admin, Operador).
    Não é o morador/visitante.
    """
    __tablename__ = 'operador'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    nome_completo = db.Column(db.String(200), nullable=False)
    is_admin = db.Column(db.Boolean, default=False, nullable=False)

    # Relacionamento com logs de auditoria
    logs_auditoria = db.relationship('LogAuditoria', backref='operador', lazy=True)

    def set_password(self, password):
        """Gera o hash da senha."""
        self.password_hash = generate_password_hash(password)
    
    def check_password(self, password):
        """Verifica se a senha fornecida bate com o hash."""
        return check_password_hash(self.password_hash, password)

    def __repr__(self):
        return f'<Operador {self.username}>'


# Tabela Associativa (helper table) para NivelAcesso <-> Dispositivo
# Um nível de acesso pode conter vários dispositivos.
# Um dispositivo pode estar em vários níveis de acesso (ex: "Leitor Portaria" está no "Nível Morador" e "Nível Funcionário")
nivel_acesso_dispositivos = db.Table('nivel_acesso_dispositivos',
    db.Column('nivel_acesso_id', db.Integer, db.ForeignKey('nivel_acesso.id'), primary_key=True),
    db.Column('dispositivo_id', db.Integer, db.ForeignKey('dispositivo.id'), primary_key=True)
)

class NivelAcesso(db.Model):
    """
    Define os grupos de permissão. Ex: "Moradores", "Visitantes", "Garagem"
    """
    __tablename__ = 'nivel_acesso'
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(100), unique=True, nullable=False)
    descricao = db.Column(db.String(255))
    
    # Relacionamento M-M com Dispositivo
    # 'dispositivos' lista quais dispositivos pertencem a este nível
    dispositivos = db.relationship('Dispositivo', secondary=nivel_acesso_dispositivos,
                                  lazy='subquery', backref=db.backref('niveis_acesso', lazy=True))
    
    # Relacionamento 1-M com Pessoa
    # 'pessoas' lista quais pessoas têm este nível de acesso
    pessoas = db.relationship('Pessoa', backref='nivel_acesso', lazy=True)

    def __repr__(self):
        return f'<NivelAcesso {self.nome}>'

# -------------------------------------------------------------------
# MODELOS DE PESSOAS E VEÍCULOS
# -------------------------------------------------------------------

class Pessoa(db.Model):
    """
    Tabela central para todos os tipos de usuários (Morador, Visitante, etc.)
    """
    __tablename__ = 'pessoa'
    id = db.Column(db.Integer, primary_key=True)
    nome_completo = db.Column(db.String(200), nullable=False)
    documento = db.Column(db.String(50), unique=True, index=True) # CPF, RG, etc.
    foto_url = db.Column(db.String(300)) # Caminho para a foto
    data_cadastro = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Este é o campo que define o tipo, como você pediu (Morador, Visitante, etc.)
    tipo_usuario = db.Column(db.String(50), nullable=False, index=True) 
    
    # Chave estrangeira para o Nível de Acesso
    nivel_acesso_id = db.Column(db.Integer, db.ForeignKey('nivel_acesso.id'), nullable=True)
    
    # Relacionamentos
    veiculos = db.relationship('Veiculo', backref='proprietario', lazy=True)
    logs_transito = db.relationship('LogTransito', backref='pessoa', lazy=True)

    def __repr__(self):
        return f'<Pessoa {self.nome_completo} ({self.tipo_usuario})>'

class Veiculo(db.Model):
    """
    Tabela de veículos, associados a uma Pessoa.
    """
    __tablename__ = 'veiculo'
    id = db.Column(db.Integer, primary_key=True)
    placa = db.Column(db.String(10), unique=True, nullable=False, index=True)
    marca = db.Column(db.String(50))
    modelo = db.Column(db.String(50))
    cor = db.Column(db.String(30))
    
    # Chave estrangeira para o proprietário (Pessoa)
    pessoa_id = db.Column(db.Integer, db.ForeignKey('pessoa.id'), nullable=True)

    def __repr__(self):
        return f'<Veiculo {self.placa}>'

# -------------------------------------------------------------------
# MODELOS DE HARDWARE E LOGS
# -------------------------------------------------------------------

class Dispositivo(db.Model):
    """
    As "Controladoras" que você mencionou (leitores, etc.)
    """
    __tablename__ = 'dispositivo'
    id = db.Column(db.Integer, primary_key=True)
    nome_local = db.Column(db.String(100), nullable=False) # Ex: "Portaria Social", "Garagem - Entrada"
    fabricante = db.Column(db.String(100)) # "Control ID", "Hikvision", "Intelbras"
    modelo = db.Column(db.String(100)) # "iDFace", "DS-K1T671MF"
    ip_address = db.Column(db.String(45)) # Suporta IPv4
    status = db.Column(db.String(50), default="Offline") # "Online", "Offline", "Manutenção"

    # 'niveis_acesso' (backref) lista quais níveis podem acessar este dispositivo
    logs_transito = db.relationship('LogTransito', backref='dispositivo', lazy=True)

    def __repr__(self):
        return f'<Dispositivo {self.nome_local} ({self.modelo})>'

class LogTransito(db.Model):
    """
    Para o "Relatório de Trânsito". Registra cada tentativa de acesso.
    """
    __tablename__ = 'log_transito'
    id = db.Column(db.Integer, primary_key=True)
    data_hora = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    direcao = db.Column(db.String(10), nullable=False) # "Entrada", "Saída"
    status_acesso = db.Column(db.String(20), nullable=False) # "Permitido", "Negado"
    
    # Chaves estrangeiras
    pessoa_id = db.Column(db.Integer, db.ForeignKey('pessoa.id'), nullable=True) # Pode ser nulo se for um acesso negado de cartão desconhecido
    dispositivo_id = db.Column(db.Integer, db.ForeignKey('dispositivo.id'), nullable=False)

class LogAuditoria(db.Model):
    """
    Para o "Relatório de Auditoria". Registra cada ação do Operador.
    """
    __tablename__ = 'log_auditoria'
    id = db.Column(db.Integer, primary_key=True)
    data_hora = db.Column(db.DateTime, default=datetime.utcnow)
    acao = db.Column(db.String(100), nullable=False) # Ex: "Login", "Criação de Usuário", "Edição de Nível de Acesso"
    descricao = db.Column(db.Text, nullable=False) # Ex: "Operador 'admin' criou o usuário 'João Silva' (ID: 10)"
    
    # Chave estrangeira
    operador_id = db.Column(db.Integer, db.ForeignKey('operador.id'), nullable=False)

# -------------------------------------------------------------------
# MODELO DE CUSTOMIZAÇÃO
# -------------------------------------------------------------------

class ConfiguracaoSistema(db.Model):
    """
    Tabela Key-Value para guardar as customizações que o admin fizer.
    Ex: chave="label_morador", valor="Residente"
    """
    __tablename__ = 'configuracao_sistema'
    id = db.Column(db.Integer, primary_key=True)
    chave = db.Column(db.String(100), unique=True, nullable=False)
    valor = db.Column(db.String(300), nullable=False)