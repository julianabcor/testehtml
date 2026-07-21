"""
API web do painel Alleanza.

Reaproveita a mesma lógica de conexão do projeto de terminal (mysql-connector
+ .env), só que devolvendo os dados em JSON para o navegador, em vez de
imprimir tabela no console.
"""
import os
from flask import Flask, jsonify, send_from_directory
import mysql.connector
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__, static_folder="public", static_url_path="")


def conectar():
    host = os.getenv("DB_HOST")
    user = os.getenv("DB_USER")
    password = os.getenv("DB_PASSWORD")
    database = os.getenv("DB_NAME")
    port = os.getenv("DB_PORT")

    conn_kwargs = dict(host=host, user=user, password=password, database=database)
    if port:
        conn_kwargs["port"] = int(port)

    ssl_ca = os.getenv("DB_SSL_CA_PATH")
    if ssl_ca:
        conn_kwargs["ssl_ca"] = ssl_ca

    return mysql.connector.connect(**conn_kwargs)


def consultar(sql):
    """Executa um SELECT e devolve a lista de linhas como dicionários."""
    conexao = conectar()
    cursor = conexao.cursor(dictionary=True)
    cursor.execute(sql)
    linhas = cursor.fetchall()
    cursor.close()
    conexao.close()
    return linhas


# ---------- Rotas da API (mesmas consultas já usadas no app de terminal) ----------

@app.get("/api/imoveis")
def api_imoveis():
    sql = """
    SELECT
        i.id_imovel,
        p.nome AS proprietario,
        t.descricao AS tipo_imovel,
        e.rua, e.numero, e.bairro, e.cidade, e.estado,
        i.valor_sugerido,
        i.status_imovel,
        i.data_cadastro
    FROM Imovel i
    JOIN Proprietario p ON i.id_proprietario = p.id_proprietario
    JOIN TipoImovel t ON i.id_tipo_imovel = t.id_tipo_imovel
    JOIN Endereco e ON i.id_endereco = e.id_endereco
    """
    return jsonify(consultar(sql))


@app.get("/api/clientes")
def api_clientes():
    sql = "SELECT id_cliente, nome, cpf, telefone, email, data_cadastro FROM Cliente"
    return jsonify(consultar(sql))


@app.get("/api/proprietarios")
def api_proprietarios():
    sql = "SELECT id_proprietario, nome, cpf_cnpj, telefone, email FROM Proprietario"
    return jsonify(consultar(sql))


@app.get("/api/corretores")
def api_corretores():
    sql = "SELECT id_corretor, nome, creci, telefone, email FROM Corretor"
    return jsonify(consultar(sql))


@app.get("/api/vendas")
def api_vendas():
    sql = """
    SELECT
        v.id_venda, c.nome AS cliente, co.nome AS corretor,
        i.id_imovel, v.data_venda, v.valor_venda
    FROM Venda v
    JOIN Cliente c ON v.id_cliente = c.id_cliente
    JOIN Corretor co ON v.id_corretor = co.id_corretor
    JOIN Imovel i ON v.id_imovel = i.id_imovel
    """
    return jsonify(consultar(sql))


@app.get("/api/alugueis")
def api_alugueis():
    sql = """
    SELECT
        a.id_aluguel, c.nome AS cliente, co.nome AS corretor,
        i.id_imovel, a.data_inicio, a.valor_aluguel
    FROM Aluguel a
    JOIN Cliente c ON a.id_cliente = c.id_cliente
    JOIN Corretor co ON a.id_corretor = co.id_corretor
    JOIN Imovel i ON a.id_imovel = i.id_imovel
    """
    return jsonify(consultar(sql))


@app.get("/api/contratos")
def api_contratos():
    sql = """
    SELECT id_contrato, id_venda, id_aluguel, data_assinatura,
           data_inicio, data_fim, clausulas
    FROM Contrato
    """
    return jsonify(consultar(sql))


# ---------- Servir os HTMLs ----------

@app.get("/")
def home():
    return send_from_directory(app.static_folder, "alleanza-painel-interno.html")


if __name__ == "__main__":
    porta = int(os.getenv("PORT", 5000))
    app.run(host="0.0.0.0", port=porta)
