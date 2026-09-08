from flask import Flask, render_template, request, redirect, url_for, flash, session
from extensions import db  
import models              
from datetime import datetime, timedelta 
from functools import wraps 
import json 
from collections import defaultdict 
from werkzeug.security import generate_password_hash 

# --- 1. CONFIGURAÇÃO INICIAL ---
app = Flask(__name__)
app.config.from_pyfile('config.py')

# --- 2. INICIALIZAÇÃO DO BANCO ---
db.init_app(app)

# --- 3. HELPERS E DECORATORS ---

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get("is_admin"):
            flash("Você não tem permissão para acessar esta página.", "error")
            return redirect(url_for("dashboard"))
        return f(*args, **kwargs)
    return decorated_function

@app.context_processor
def inject_config():
    try:
        config_morador = models.ConfiguracaoSistema.query.filter_by(chave='label_morador').first()
        config_visitante = models.ConfiguracaoSistema.query.filter_by(chave='label_visitante').first()
        config_prestador = models.ConfiguracaoSistema.query.filter_by(chave='label_prestador').first()
        config_veiculo = models.ConfiguracaoSistema.query.filter_by(chave='label_veiculo').first()
        config_funcionario = models.ConfiguracaoSistema.query.filter_by(chave='label_funcionario').first()

        labels = {
            'morador': config_morador.valor if config_morador else "Morador",
            'visitante': config_visitante.valor if config_visitante else "Visitante",
            'prestador': config_prestador.valor if config_prestador else "Prestador de Serviço",
            'veiculo': config_veiculo.valor if config_veiculo else "Veículos",
            'funcionario': config_funcionario.valor if config_funcionario else "Funcionários"
        }
    except Exception:
        labels = {
            'morador': "Morador", 'visitante': "Visitante", 'prestador': "Prestador de Serviço",
            'veiculo': "Veículos", 'funcionario': "Funcionários"
        }
    return dict(labels=labels)


# --- ROTAS DE AUTENTICAÇÃO ---

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")
        
        operador = models.Operador.query.filter_by(username=username).first()

        if operador and operador.check_password(password):
            session["logged_in"] = True
            session["username"] = operador.username
            session["operador_id"] = operador.id
            session["is_admin"] = operador.is_admin
            
            try:
                log_login = models.LogAuditoria(
                    data_hora=datetime.now(),
                    acao="Login",
                    descricao=f"Operador '{operador.username}' efetuou login.",
                    operador_id=operador.id
                )
                db.session.add(log_login)
                db.session.commit()
            except Exception as e:
                db.session.rollback()
                flash(f"Erro ao registrar log de login: {e}", "error")
                
            return redirect(url_for("dashboard"))
        else:
            flash("Usuário ou senha inválidos", "error")
            
    return render_template("login.html")

@app.route("/logout")
def logout():
    if session.get("logged_in"):
        try:
            log_logout = models.LogAuditoria(
                data_hora=datetime.now(),
                acao="Logout",
                descricao=f"Operador '{session['username']}' efetuou logout.",
                operador_id=session['operador_id']
            )
            db.session.add(log_logout)
            db.session.commit()
        except Exception:
            db.session.rollback()

    session.clear()
    return redirect(url_for("login"))


# --- ROTAS DO SISTEMA ---

@app.before_request
def check_login():
    if not session.get("logged_in") and request.endpoint not in ("login", "static"):
        return redirect(url_for("login"))

# --- ROTA DE DASHBOARD ---
@app.route("/")
@app.route("/dashboard")
def dashboard():
    try:
        total_usuarios = models.Pessoa.query.count()
        total_dispositivos = models.Dispositivo.query.count()
        dispositivos_online = models.Dispositivo.query.filter_by(status="Online").count()
        dispositivos_offline = models.Dispositivo.query.filter_by(status="Offline").count()
        total_niveis = models.NivelAcesso.query.count()

        todas_pessoas = models.Pessoa.query.order_by(models.Pessoa.nome_completo).all()
        todos_dispositivos = models.Dispositivo.query.order_by(models.Dispositivo.nome_local).all()

        # Lógica do Gráfico (Últimos 7 dias)
        hoje = datetime.now()
        contagem_dias = {} 
        
        for i in range(6, -1, -1):
            data_passada = hoje - timedelta(days=i)
            chave_data = data_passada.strftime('%d/%m') 
            contagem_dias[chave_data] = 0

        data_limite = (hoje - timedelta(days=6)).replace(hour=0, minute=0, second=0, microsecond=0)
        logs_recentes = models.LogTransito.query.filter(models.LogTransito.data_hora >= data_limite).all()

        for log in logs_recentes:
            chave_data = log.data_hora.strftime('%d/%m')
            if chave_data in contagem_dias:
                contagem_dias[chave_data] += 1
        
        labels_grafico = list(contagem_dias.keys())
        valores_grafico = list(contagem_dias.values())

    except Exception as e:
        print(f"Erro no dashboard: {e}")
        total_usuarios, total_dispositivos, dispositivos_online, dispositivos_offline, total_niveis = 0, 0, 0, 0, 0
        todas_pessoas, todos_dispositivos, labels_grafico, valores_grafico = [], [], [], []

    return render_template("dashboard.html",
                           total_usuarios=total_usuarios,
                           total_dispositivos=total_dispositivos,
                           dispositivos_online=dispositivos_online,
                           dispositivos_offline=dispositivos_offline,
                           total_niveis=total_niveis,
                           todas_pessoas=todas_pessoas,
                           todos_dispositivos=todos_dispositivos,
                           chart_labels=labels_grafico,   
                           chart_values=valores_grafico   
                           )

# --- ROTA DE SIMULAÇÃO ---
@app.route("/simular_acesso", methods=["POST"])
def simular_acesso():
    try:
        pessoa_id = request.form.get("pessoa_id")
        dispositivo_id = request.form.get("dispositivo_id")
        
        # CORREÇÃO: Como removemos o campo do HTML, definimos um padrão aqui
        direcao = "Entrada"

        pessoa = models.Pessoa.query.get(pessoa_id)
        dispositivo = models.Dispositivo.query.get(dispositivo_id)

        if not pessoa or not dispositivo:
            flash("Pessoa ou Dispositivo não encontrado.", "error")
            return redirect(url_for("dashboard"))

        status_final = "Negado"
        
        if pessoa.nivel_acesso:
            if dispositivo in pessoa.nivel_acesso.dispositivos:
                status_final = "Permitido"

        novo_log = models.LogTransito(
            data_hora=datetime.now(),
            direcao=direcao,
            status_acesso=status_final,
            pessoa_id=pessoa.id,
            dispositivo_id=dispositivo.id
        )
        db.session.add(novo_log)
        
        log_auditoria = models.LogAuditoria(
            data_hora=datetime.now(),
            acao="Simulação de Acesso",
            descricao=f"Operador '{session['username']}' simulou acesso: {status_final} para '{pessoa.nome_completo}' em '{dispositivo.nome_local}'.",
            operador_id=session['operador_id']
        )
        db.session.add(log_auditoria)
        
        db.session.commit()

        if status_final == "Permitido":
            flash(f"Acesso Permitido para {pessoa.nome_completo} no dispositivo {dispositivo.nome_local}.", "success")
        else:
            flash(f"Acesso Negado para {pessoa.nome_completo} no dispositivo {dispositivo.nome_local}.", "error")

    except Exception as e:
        db.session.rollback()
        flash(f"Erro ao simular acesso: {e}", "error")

    return redirect(url_for("dashboard"))


# --- ROTA DE USUÁRIOS ---
@app.route("/usuarios", methods=["GET", "POST"])
def usuarios():
    config = inject_config()['labels']
    
    if request.method == "POST":
        try:
            nome = request.form.get("nome_completo")
            documento = request.form.get("documento")
            tipo_usuario = request.form.get("tipo_usuario")
            nivel_id = request.form.get("nivel_acesso_id")
            
            novo_usuario = models.Pessoa(
                nome_completo=nome,
                documento=documento,
                tipo_usuario=tipo_usuario,
                nivel_acesso_id=nivel_id if (nivel_id and nivel_id != "") else None
            )
            db.session.add(novo_usuario)
            
            log_auditoria = models.LogAuditoria(
                data_hora=datetime.now(),
                acao="Criação de Usuário",
                descricao=f"Operador '{session['username']}' criou o usuário '{nome}' (Tipo: {tipo_usuario}).",
                operador_id=session['operador_id']
            )
            db.session.add(log_auditoria)
            db.session.commit()
            flash(f"{tipo_usuario} '{nome}' cadastrado com sucesso!", "success")
        except Exception as e:
            db.session.rollback() 
            flash(f"Erro ao cadastrar: {e}", "error")
        return redirect(url_for("usuarios"))

    lista_usuarios = models.Pessoa.query.order_by(models.Pessoa.nome_completo).all()
    lista_niveis = models.NivelAcesso.query.order_by(models.NivelAcesso.nome).all()
    
    return render_template("usuarios.html", moradores=lista_usuarios, niveis_acesso=lista_niveis)

@app.route("/usuarios/editar/<int:id>", methods=["GET", "POST"])
def editar_usuario(id):
    usuario = models.Pessoa.query.get_or_404(id)
    
    if request.method == "POST":
        try:
            usuario.nome_completo = request.form.get("nome_completo")
            usuario.documento = request.form.get("documento")
            usuario.tipo_usuario = request.form.get("tipo_usuario")
            nivel_id = request.form.get("nivel_acesso_id")
            usuario.nivel_acesso_id = nivel_id if (nivel_id and nivel_id != "") else None

            log_auditoria = models.LogAuditoria(
                data_hora=datetime.now(),
                acao="Edição de Usuário",
                descricao=f"Operador '{session['username']}' editou o usuário '{usuario.nome_completo}' (ID: {usuario.id}).",
                operador_id=session['operador_id']
            )
            db.session.add(log_auditoria)
            db.session.commit()
            flash(f"Usuário '{usuario.nome_completo}' atualizado com sucesso!", "success")
            return redirect(url_for("usuarios"))
        except Exception as e:
            db.session.rollback()
            flash(f"Erro ao atualizar: {e}", "error")

    lista_niveis = models.NivelAcesso.query.order_by(models.NivelAcesso.nome).all()
    labels = inject_config()['labels'] 
    tipos_disponiveis = [labels['morador'], labels['visitante'], labels['prestador'], labels['funcionario'], labels['veiculo']]

    return render_template("editar_usuario.html", usuario=usuario, niveis_acesso=lista_niveis, tipos=tipos_disponiveis)

@app.route("/usuarios/excluir/<int:id>")
def excluir_usuario(id):
    try:
        usuario = models.Pessoa.query.get_or_404(id)
        nome_removido = usuario.nome_completo
        db.session.delete(usuario)
        log_auditoria = models.LogAuditoria(
            data_hora=datetime.now(),
            acao="Exclusão de Usuário",
            descricao=f"Operador '{session['username']}' excluiu o usuário '{nome_removido}' (ID: {id}).",
            operador_id=session['operador_id']
        )
        db.session.add(log_auditoria)
        db.session.commit()
        flash(f"Usuário '{nome_removido}' excluído com sucesso.", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Erro ao excluir: {e}", "error")
    return redirect(url_for("usuarios"))


# --- ROTA DE DISPOSITIVOS ---
@app.route("/dispositivos", methods=["GET", "POST"])
def dispositivos():
    catalogo_equipamentos = {
        "ControlID": ["iDAccess", "iDAccess Nano ENTERPRISE", "iDAccess Nano PRO", "iDAccess Pro", "iDBlock", "iDBlock com Urna", "iDBox", "iDFace", "iDFit", "iDFlex ENTERPRISE", "iDFlex PRO", "iDUHF", "REP iDClass"],
        "Hikvision": ["DS-K1T341AM (Face)", "DS-K1T671M (Face Pro)", "DS-K1T331 (Face Mini)", "DS-K1T804 (Bio)", "DS-K1T501 (Video Intercom)"],
        "Intelbras": ["SS 3530 MF FACE", "SS 5530 MF FACE", "SS 311 MF", "Bio Inox Plus", "Digiprox SA 202", "Controladora 4 Portas"]
    }

    if request.method == "POST":
        try:
            nome_local = request.form.get("nome_local")
            fabricante = request.form.get("fabricante")
            modelo = request.form.get("modelo")
            ip_address = request.form.get("ip_address")

            novo_dispositivo = models.Dispositivo(
                nome_local=nome_local, fabricante=fabricante, modelo=modelo, ip_address=ip_address
            )
            db.session.add(novo_dispositivo)

            log_auditoria = models.LogAuditoria(
                data_hora=datetime.now(),
                acao="Criação de Dispositivo",
                descricao=f"Operador '{session['username']}' criou o dispositivo '{nome_local}' (Modelo: {modelo}).",
                operador_id=session['operador_id']
            )
            db.session.add(log_auditoria)
            db.session.commit()
            flash(f"Dispositivo '{nome_local}' cadastrado com sucesso!", "success")

        except Exception as e:
            db.session.rollback()
            flash(f"Erro ao cadastrar dispositivo: {e}", "error")
        return redirect(url_for("dispositivos"))

    lista_dispositivos = models.Dispositivo.query.all()
    return render_template("dispositivos.html", dispositivos=lista_dispositivos, catalogo_equipamentos=catalogo_equipamentos)

# --- NOVA ROTA: EDITAR DISPOSITIVO ---
@app.route("/dispositivos/editar/<int:id>", methods=["GET", "POST"])
@admin_required
def editar_dispositivo(id):
    dispositivo = models.Dispositivo.query.get_or_404(id)

    # Catálogo para preencher os selects
    catalogo_equipamentos = {
        "ControlID": ["iDAccess", "iDAccess Nano ENTERPRISE", "iDAccess Nano PRO", "iDAccess Pro", "iDBlock", "iDBlock com Urna", "iDBox", "iDFace", "iDFit", "iDFlex ENTERPRISE", "iDFlex PRO", "iDUHF", "REP iDClass"],
        "Hikvision": ["DS-K1T341AM (Face)", "DS-K1T671M (Face Pro)", "DS-K1T331 (Face Mini)", "DS-K1T804 (Bio)", "DS-K1T501 (Video Intercom)"],
        "Intelbras": ["SS 3530 MF FACE", "SS 5530 MF FACE", "SS 311 MF", "Bio Inox Plus", "Digiprox SA 202", "Controladora 4 Portas"]
    }

    if request.method == "POST":
        try:
            dispositivo.nome_local = request.form.get("nome_local")
            dispositivo.fabricante = request.form.get("fabricante")
            dispositivo.modelo = request.form.get("modelo")
            dispositivo.ip_address = request.form.get("ip_address")

            log_auditoria = models.LogAuditoria(
                data_hora=datetime.now(),
                acao="Edição de Dispositivo",
                descricao=f"Operador '{session['username']}' editou o dispositivo '{dispositivo.nome_local}' (ID: {dispositivo.id}).",
                operador_id=session['operador_id']
            )
            db.session.add(log_auditoria)
            db.session.commit()
            
            flash(f"Dispositivo '{dispositivo.nome_local}' atualizado com sucesso!", "success")
            return redirect(url_for("dispositivos"))

        except Exception as e:
            db.session.rollback()
            flash(f"Erro ao atualizar dispositivo: {e}", "error")

    return render_template("editar_dispositivo.html", dispositivo=dispositivo, catalogo_equipamentos=catalogo_equipamentos)

@app.route("/dispositivos/excluir/<int:id>")
@admin_required
def excluir_dispositivo(id):
    try:
        dispositivo = models.Dispositivo.query.get_or_404(id)
        nome_dispositivo = dispositivo.nome_local
        db.session.delete(dispositivo)
        
        log_auditoria = models.LogAuditoria(
            data_hora=datetime.now(),
            acao="Exclusão de Dispositivo",
            descricao=f"Operador '{session['username']}' excluiu o dispositivo '{nome_dispositivo}' (ID: {id}).",
            operador_id=session['operador_id']
        )
        db.session.add(log_auditoria)
        db.session.commit()
        flash(f"Dispositivo '{nome_dispositivo}' excluído com sucesso.", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Erro ao excluir dispositivo: {e}", "error")
    return redirect(url_for("dispositivos"))


# --- ROTA DE RELATÓRIOS ---
@app.route("/relatorios")
def relatorios():
    try:
        logs_de_transito = models.LogTransito.query.order_by(models.LogTransito.data_hora.desc()).limit(50).all()
        niveis_com_pessoas = models.NivelAcesso.query.options(db.joinedload(models.NivelAcesso.pessoas)).order_by(models.NivelAcesso.nome).all()
        pessoas_sem_nivel = models.Pessoa.query.filter(models.Pessoa.nivel_acesso_id == None).order_by(models.Pessoa.nome_completo).all()
        logs_de_auditoria = models.LogAuditoria.query.options(db.joinedload(models.LogAuditoria.operador)).order_by(models.LogAuditoria.data_hora.desc()).limit(50).all()
    except Exception as e:
        flash(f"Erro ao carregar relatórios: {e}", "error")
        logs_de_transito, niveis_com_pessoas, pessoas_sem_nivel, logs_de_auditoria = [], [], [], []

    return render_template("relatorios.html", logs=logs_de_transito, niveis_com_pessoas=niveis_com_pessoas, pessoas_sem_nivel=pessoas_sem_nivel, logs_de_auditoria=logs_de_auditoria)


# --- ROTA DE CONFIGURAÇÕES (COM A CORREÇÃO DO NOME COMPLETO) ---
@app.route("/configuracoes", methods=["GET", "POST"])
def configuracoes():
    lista_niveis = models.NivelAcesso.query.all()
    lista_operadores = models.Operador.query.all()
    labels_atuais = inject_config()['labels']

    if request.method == "POST":
        form_name = request.form.get("form_name")

        # 1. CRIAR NÍVEL
        if form_name == "nivel_acesso":
            try:
                nome_nivel = request.form.get("nome_nivel")
                desc_nivel = request.form.get("desc_nivel")
                novo_nivel = models.NivelAcesso(nome=nome_nivel, descricao=desc_nivel)
                db.session.add(novo_nivel)
                log_auditoria = models.LogAuditoria(
                    data_hora=datetime.now(), acao="Criação de Nível",
                    descricao=f"Criou nível '{nome_nivel}'.", operador_id=session['operador_id']
                )
                db.session.add(log_auditoria)
                db.session.commit()
                flash(f"Nível '{nome_nivel}' criado com sucesso!", "success")
            except Exception as e:
                db.session.rollback()
                flash(f"Erro ao criar nível: {e}", "error")
        
        # 2. CUSTOMIZAÇÃO
        elif form_name == "customizacao" and session.get("is_admin"):
            try:
                chaves = ['label_morador', 'label_visitante', 'label_prestador', 'label_veiculo', 'label_funcionario']
                for chave in chaves:
                    valor = request.form.get(chave)
                    if valor: 
                        config = models.ConfiguracaoSistema.query.filter_by(chave=chave).first()
                        if config: config.valor = valor
                        else: db.session.add(models.ConfiguracaoSistema(chave=chave, valor=valor))
                
                log_auditoria = models.LogAuditoria(
                    data_hora=datetime.now(), acao="Customização",
                    descricao="Atualizou rótulos do sistema.", operador_id=session['operador_id']
                )
                db.session.add(log_auditoria)
                db.session.commit()
                flash("Customização salva com sucesso!", "success")
            except Exception as e:
                db.session.rollback()
                flash(f"Erro na customização: {e}", "error")

        # 3. NOVO OPERADOR (CORRIGIDO)
        elif form_name == "novo_operador" and session.get("is_admin"):
            try:
                # AGORA CAPTURA O NOME COMPLETO DO FORMULÁRIO
                nome_completo = request.form.get("nome_completo") 
                username = request.form.get("username")
                password = request.form.get("password")
                is_admin = True if request.form.get("is_admin") == 'on' else False

                if models.Operador.query.filter_by(username=username).first():
                    flash("Erro: Nome de usuário já existe.", "error")
                else:
                    senha_hash = generate_password_hash(password)
                    
                    # ENVIA TODOS OS CAMPOS PARA O BANCO
                    novo_operador = models.Operador(
                        nome_completo=nome_completo, 
                        username=username, 
                        password_hash=senha_hash, 
                        is_admin=is_admin
                    )
                    db.session.add(novo_operador)
                    
                    log_auditoria = models.LogAuditoria(
                        data_hora=datetime.now(), acao="Criação de Operador",
                        descricao=f"Criou operador '{username}' (Admin: {is_admin}).", operador_id=session['operador_id']
                    )
                    db.session.add(log_auditoria)
                    db.session.commit()
                    flash(f"Operador '{username}' criado com sucesso!", "success")
            except Exception as e:
                db.session.rollback()
                flash(f"Erro ao criar operador: {e}", "error")

        return redirect(url_for("configuracoes"))

    return render_template("configuracoes.html", 
                           niveis_acesso=lista_niveis, 
                           labels_atuais=labels_atuais,
                           operadores=lista_operadores)

@app.route("/configuracoes/nivel/editar/<int:id>", methods=["GET", "POST"])
@admin_required
def editar_nivel_acesso(id):
    nivel = models.NivelAcesso.query.get_or_404(id)
    if request.method == "POST":
        try:
            dispositivos_selecionados_ids = request.form.getlist("dispositivo_ids")
            nivel.dispositivos = []
            desc_dispositivos = []
            for device_id in dispositivos_selecionados_ids:
                device = models.Dispositivo.query.get(device_id)
                if device:
                    nivel.dispositivos.append(device)
                    desc_dispositivos.append(device.nome_local)
            
            desc_log = f"Operador '{session['username']}' editou o nível '{nivel.nome}'. Dispositivos: {', '.join(desc_dispositivos) or 'Nenhum'}."
            log_auditoria = models.LogAuditoria(
                data_hora=datetime.now(),
                acao="Edição de Nível de Acesso",
                descricao=desc_log,
                operador_id=session['operador_id']
            )
            db.session.add(log_auditoria)
            db.session.commit()
            flash(f"Nível '{nivel.nome}' atualizado com sucesso.", "success")
            return redirect(url_for("configuracoes"))
        except Exception as e:
            db.session.rollback()
            flash(f"Erro ao atualizar o nível: {e}", "error")
            return redirect(url_for("configuracoes"))

    todos_dispositivos = models.Dispositivo.query.order_by(models.Dispositivo.nome_local).all()
    return render_template("editar_nivel.html", nivel=nivel, todos_dispositivos=todos_dispositivos)

@app.route("/configuracoes/nivel/excluir/<int:id>")
@admin_required
def excluir_nivel_acesso(id):
    try:
        nivel = models.NivelAcesso.query.get_or_404(id)
        nome_nivel = nivel.nome
        if nivel.pessoas:
            flash(f"Erro: O nível '{nivel.nome}' está em uso por {len(nivel.pessoas)} usuário(s).", "error")
            return redirect(url_for("configuracoes"))
        db.session.delete(nivel)
        log_auditoria = models.LogAuditoria(
            data_hora=datetime.now(),
            acao="Exclusão de Nível de Acesso",
            descricao=f"Operador '{session['username']}' excluiu o nível de acesso '{nome_nivel}' (ID: {id}).",
            operador_id=session['operador_id']
        )
        db.session.add(log_auditoria)
        db.session.commit()
        flash(f"Nível '{nome_nivel}' excluído com sucesso.", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Erro ao excluir nível: {e}", "error")
    return redirect(url_for("configuracoes"))

# --- ROTA: EXCLUIR OPERADOR ---
@app.route("/configuracoes/operador/excluir/<int:id>")
@admin_required
def excluir_operador(id):
    if id == session.get("operador_id"):
        flash("Você não pode excluir seu próprio usuário enquanto está logado.", "error")
        return redirect(url_for("configuracoes"))

    try:
        operador = models.Operador.query.get_or_404(id)
        nome = operador.username
        db.session.delete(operador)
        
        db.session.add(models.LogAuditoria(
            data_hora=datetime.now(), acao="Exclusão de Operador", 
            descricao=f"Excluiu operador '{nome}'", operador_id=session['operador_id']
        ))
        db.session.commit()
        flash(f"Operador '{nome}' excluído.", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Erro ao excluir: {e}", "error")

    return redirect(url_for("configuracoes"))

@app.route("/sobre")
def sobre():
    return render_template("sobre.html")

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)