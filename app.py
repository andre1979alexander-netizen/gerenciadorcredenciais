from flask import Flask, render_template, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime

app = Flask(__name__)
app.config['SECRET_KEY'] = 'chave_secreta_super_segura_para_o_escritorio'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///assessoria_contabil_v3.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# ==========================================
# CONFIGURAÇÃO DO GERENCIADOR DE LOGIN
# ==========================================
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login' # Define para onde mandar o usuário se ele não estiver logado
login_manager.login_message = "Por favor, faça login para acessar o sistema."
login_manager.login_message_category = "warning"

@login_manager.user_loader
def load_user(user_id):
    return Usuario.query.get(int(user_id))

# ==========================================
# MODELOS DE BANCO DE DADOS
# ==========================================

# Nova Tabela para os Colaboradores do Escritório
class Usuario(UserMixin, db.Model):
    __tablename__ = 'usuarios'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), nullable=False, unique=True)
    nome = db.Column(db.String(100), nullable=False)
    senha_hash = db.Column(db.String(200), nullable=False)

class Cliente(db.Model):
    __tablename__ = 'clientes'
    id = db.Column(db.Integer, primary_key=True)
    nome_completo = db.Column(db.String(100), nullable=False)
    cpf = db.Column(db.String(14), nullable=False, unique=True)
    telefone = db.Column(db.String(20), nullable=True)
    
    acessos = db.relationship('AcessoPlataforma', backref='cliente', lazy=True, cascade="all, delete-orphan")

class AcessoPlataforma(db.Model):
    __tablename__ = 'acessos_plataforma'
    id = db.Column(db.Integer, primary_key=True)
    plataforma = db.Column(db.String(100), nullable=False)
    cnpj_vinculado = db.Column(db.String(18), nullable=True) 
    usuario_login = db.Column(db.String(100), nullable=False)
    senha_acesso = db.Column(db.String(100), nullable=False)
    observacoes = db.Column(db.Text, nullable=True)
    data_atualizacao = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    cliente_id = db.Column(db.Integer, db.ForeignKey('clientes.id'), nullable=False)


# Criação das tabelas e do usuário padrão do escritório
with app.app_context():
    db.create_all()
    # Se não houver nenhum usuário cadastrado, cria o primeiro admin
    if not Usuario.query.filter_by(username='admin').first():
        senha_criptografada = generate_password_hash('contabil123', method='pbkdf2:sha256')
        usuario_padrao = Usuario(username='admin', nome='Administrador Contábil', senha_hash=senha_criptografada)
        db.session.add(usuario_padrao)
        db.session.commit()

# ==========================================
# ROTAS DE AUTENTICAÇÃO
# ==========================================

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
        
    if request.method == 'POST':
        username = request.form.get('username').strip()
        senha = request.form.get('senha')
        
        usuario = Usuario.query.filter_by(username=username).first()
        
        # Verifica se o usuário existe e se a senha bate com o hash criptografado
        if usuario and check_password_hash(usuario.senha_hash, senha):
            login_user(usuario)
            flash(f'Bem-vindo de volta, {usuario.nome}!', 'success')
            return redirect(url_for('index'))
        else:
            flash('Usuário ou senha incorretos.', 'danger')
            
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Sessão encerrada com segurança.', 'info')
    return redirect(url_for('login'))

# ==========================================
# ROTAS DO SISTEMA (AGORA PROTEGIDAS)
# ==========================================

@app.route('/')
@login_required # Garante que só acessa se estiver logado
def index():
    busca = request.args.get('search', '')
    if busca:
        clientes = Cliente.query.filter(
            (Cliente.nome_completo.like(f'%{busca}%')) | 
            (Cliente.cpf.like(f'%{busca}%'))
        ).all()
    else:
        clientes = Cliente.query.order_by(Cliente.nome_completo).all()
    return render_template('index.html', clientes=clientes, busca=busca)


@app.route('/cliente/<int:id>')
@login_required
def detalhes_cliente(id):
    cliente = Cliente.query.get_or_404(id)
    
    # LISTA ATUALIZADA COM AS NOVAS PLATAFORMAS SOLICITADAS
    plataformas_disponiveis = [
        "Gov.br (Pessoal)", 
        "Simples Nacional (Empresa)", 
        "Portal NFE MEI Nacional", 
        "Portal NFS Nacional", 
        "Sefaz SP", 
        "GIA", 
        "Prefeitura (ISS)", 
        "Emissor SEBRAE (Serviços)", 
        "Emissor SEBRAE (Produtos)", 
        "Empregador Doméstico", 
        "PAT Alimentação", 
        "Regularize", 
        "Parcelamento Procuradoria", 
        "Certificado Digital (A1/A3)", 
        "e-CAC (Receita Federal)"
    ]
    return render_template('detalhes.html', cliente=cliente, plataformas=plataformas_disponiveis)


@app.route('/cadastrar_cliente', methods=['GET', 'POST'])
@login_required
def cadastrar_cliente():
    if request.method == 'POST':
        nome_completo = request.form.get('nome_completo')
        cpf = request.form.get('cpf')
        telefone = request.form.get('telefone')

        if Cliente.query.filter_by(cpf=cpf).first():
            flash('Este CPF já está cadastrado no sistema!', 'danger')
            return redirect(url_for('cadastrar_cliente'))

        novo_cliente = Cliente(nome_completo=nome_completo, cpf=cpf, telefone=telefone)
        db.session.add(novo_cliente)
        db.session.commit()
        flash('Cliente cadastrado com sucesso!', 'success')
        return redirect(url_for('index'))

    return render_template('cadastrar_cliente.html')


@app.route('/cliente/<int:cliente_id>/adicionar_acesso', methods=['POST'])
@login_required
def adicionar_acesso(cliente_id):
    cliente = Cliente.query.get_or_404(cliente_id)
    
    plataforma = request.form.get('plataforma')
    cnpj_vinculado = request.form.get('cnpj_vinculado')
    usuario_login = request.form.get('usuario_login')
    senha_acesso = request.form.get('senha_acesso')
    observacoes = request.form.get('observacoes')

    novo_acesso = AcessoPlataforma(
        plataforma=plataforma,
        cnpj_vinculado=cnpj_vinculado if cnpj_vinculado else None,
        usuario_login=usuario_login,
        senha_acesso=senha_acesso,
        observacoes=observacoes,
        cliente_id=cliente.id
    )
    
    db.session.add(novo_acesso)
    db.session.commit()
    flash(f'Acesso de {plataforma} adicionado!', 'success')
    return redirect(url_for('detalhes_cliente', id=cliente.id))


@app.route('/deletar_acesso/<int:acesso_id>', methods=['POST'])
@login_required
def deletar_acesso(acesso_id):
    acesso = AcessoPlataforma.query.get_or_404(acesso_id)
    cliente_id = acesso.cliente_id
    db.session.delete(acesso)
    db.session.commit()
    flash('Acesso removido com sucesso.', 'warning')
    return redirect(url_for('detalhes_cliente', id=cliente_id))


@app.route('/deletar_cliente/<int:id>', methods=['POST'])
@login_required
def deletar_cliente(id):
    cliente = Cliente.query.get_or_404(id)
    nome_removido = cliente.nome_completo
    db.session.delete(cliente)
    db.session.commit()
    flash(f'Cliente "{nome_removido}" removido.', 'danger')
    return redirect(url_for('index'))


if __name__ == '__main__':
    app.run(debug=True)