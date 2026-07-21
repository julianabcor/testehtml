"""
API web do painel Alleanza.

Reaproveita a mesma lógica de conexão do projeto de terminal (mysql-connector
+ .env), devolvendo/recebendo dados em JSON para o navegador, em vez de
ler/imprimir tabela no console.
"""
import os
from flask import Flask, jsonify, request, send_from_directory
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
    if ssl_ca and os.path.exists(ssl_ca):
        # Temos o certificado da Aiven: conexão criptografada E com verificação
        # de identidade do servidor (mais seguro).
        conn_kwargs["ssl_ca"] = ssl_ca
        conn_kwargs["ssl_verify_cert"] = True
    else:
        # Sem o certificado por enquanto: ainda assim tenta conexão
        # criptografada, só sem verificar a identidade do servidor.
        conn_kwargs["ssl_verify_cert"] = False

    return mysql.connector.connect(**conn_kwargs)


def consultar(sql, valores=None):
    """Executa um SELECT e devolve a lista de linhas como dicionários."""
    conexao = conectar()
    cursor = conexao.cursor(dictionary=True)
    cursor.execute(sql, valores or ())
    linhas = cursor.fetchall()
    cursor.close()
    conexao.close()
    return linhas


def executar(sql, valores=None):
    """Executa um INSERT/UPDATE/DELETE e devolve (id_gerado, linhas_afetadas)."""
    conexao = conectar()
    cursor = conexao.cursor()
    try:
        cursor.execute(sql, valores or ())
        conexao.commit()
        novo_id = cursor.lastrowid
        afetadas = cursor.rowcount
        return novo_id, afetadas
    except mysql.connector.errors.IntegrityError as e:
        conexao.rollback()
        raise ValueError(str(e))
    finally:
        cursor.close()
        conexao.close()


def campo_obrigatorio_faltando(dados, campos):
    faltando = [c for c in campos if not dados.get(c)]
    return faltando


# ============================================================
#  IMÓVEIS  (+ Endereço e TipoImovel de apoio)
# ============================================================

@app.get("/api/imoveis")
def listar_imoveis():
    sql = """
    SELECT
        i.id_imovel,
        i.id_proprietario, p.nome AS proprietario,
        i.id_tipo_imovel, t.descricao AS tipo_imovel,
        i.id_endereco, e.rua, e.numero, e.bairro, e.cidade, e.estado, e.cep,
        i.valor_sugerido,
        i.status_imovel,
        i.data_cadastro
    FROM Imovel i
    JOIN Proprietario p ON i.id_proprietario = p.id_proprietario
    JOIN TipoImovel t ON i.id_tipo_imovel = t.id_tipo_imovel
    JOIN Endereco e ON i.id_endereco = e.id_endereco
    ORDER BY i.id_imovel DESC
    """
    return jsonify(consultar(sql))


@app.post("/api/imoveis")
def criar_imovel():
    dados = request.get_json(force=True) or {}
    faltando = campo_obrigatorio_faltando(
        dados, ["id_proprietario", "id_tipo_imovel", "valor_sugerido", "status_imovel"]
    )
    if faltando:
        return jsonify({"erro": f"Campos obrigatórios faltando: {', '.join(faltando)}"}), 400

    try:
        # Se vier um endereço novo (objeto), cria o Endereco primeiro.
        id_endereco = dados.get("id_endereco")
        if not id_endereco:
            endereco = dados.get("endereco") or {}
            faltando_end = campo_obrigatorio_faltando(endereco, ["rua"])
            if faltando_end:
                return jsonify({"erro": "Informe id_endereco existente ou um objeto 'endereco' com pelo menos 'rua'."}), 400
            id_endereco, _ = executar(
                """INSERT INTO Endereco (rua, numero, bairro, cidade, estado, cep)
                   VALUES (%s,%s,%s,%s,%s,%s)""",
                (endereco.get("rua"), endereco.get("numero"), endereco.get("bairro"),
                 endereco.get("cidade"), endereco.get("estado"), endereco.get("cep")),
            )

        novo_id, _ = executar(
            """INSERT INTO Imovel (id_proprietario, id_tipo_imovel, id_endereco, valor_sugerido, status_imovel)
               VALUES (%s,%s,%s,%s,%s)""",
            (dados["id_proprietario"], dados["id_tipo_imovel"], id_endereco,
             dados["valor_sugerido"], dados["status_imovel"]),
        )
        return jsonify({"id_imovel": novo_id, "id_endereco": id_endereco}), 201
    except ValueError as e:
        return jsonify({"erro": f"Erro de integridade: {e}"}), 400


@app.put("/api/imoveis/<int:id_imovel>")
def atualizar_imovel(id_imovel):
    dados = request.get_json(force=True) or {}
    faltando = campo_obrigatorio_faltando(
        dados, ["id_proprietario", "id_tipo_imovel", "id_endereco", "valor_sugerido", "status_imovel"]
    )
    if faltando:
        return jsonify({"erro": f"Campos obrigatórios faltando: {', '.join(faltando)}"}), 400
    try:
        _, afetadas = executar(
            """UPDATE Imovel SET id_proprietario=%s, id_tipo_imovel=%s, id_endereco=%s,
               valor_sugerido=%s, status_imovel=%s WHERE id_imovel=%s""",
            (dados["id_proprietario"], dados["id_tipo_imovel"], dados["id_endereco"],
             dados["valor_sugerido"], dados["status_imovel"], id_imovel),
        )
        if afetadas == 0:
            return jsonify({"erro": "Imóvel não encontrado"}), 404
        return jsonify({"ok": True})
    except ValueError as e:
        return jsonify({"erro": f"Erro de integridade: {e}"}), 400


@app.delete("/api/imoveis/<int:id_imovel>")
def deletar_imovel(id_imovel):
    try:
        _, afetadas = executar("DELETE FROM Imovel WHERE id_imovel=%s", (id_imovel,))
        if afetadas == 0:
            return jsonify({"erro": "Imóvel não encontrado"}), 404
        return jsonify({"ok": True})
    except ValueError:
        return jsonify({"erro": "Não é possível excluir: este imóvel está associado a visitas, anúncios, documentos, vendas ou aluguéis."}), 409


@app.get("/api/tipos_imovel")
def listar_tipos_imovel():
    return jsonify(consultar("SELECT id_tipo_imovel, descricao FROM TipoImovel"))


@app.get("/api/enderecos")
def listar_enderecos():
    return jsonify(consultar("SELECT id_endereco, rua, numero, bairro, cidade, estado, cep FROM Endereco"))


# ============================================================
#  CLIENTES
# ============================================================

@app.get("/api/clientes")
def listar_clientes():
    return jsonify(consultar(
        "SELECT id_cliente, nome, cpf, telefone, email, data_cadastro FROM Cliente ORDER BY id_cliente DESC"
    ))


@app.post("/api/clientes")
def criar_cliente():
    dados = request.get_json(force=True) or {}
    faltando = campo_obrigatorio_faltando(dados, ["nome", "cpf"])
    if faltando:
        return jsonify({"erro": f"Campos obrigatórios faltando: {', '.join(faltando)}"}), 400
    try:
        novo_id, _ = executar(
            "INSERT INTO Cliente (nome, cpf, telefone, email) VALUES (%s,%s,%s,%s)",
            (dados["nome"], dados["cpf"], dados.get("telefone"), dados.get("email")),
        )
        return jsonify({"id_cliente": novo_id}), 201
    except ValueError as e:
        return jsonify({"erro": f"Erro de integridade (CPF duplicado?): {e}"}), 400


@app.put("/api/clientes/<int:id_cliente>")
def atualizar_cliente(id_cliente):
    dados = request.get_json(force=True) or {}
    faltando = campo_obrigatorio_faltando(dados, ["nome", "cpf"])
    if faltando:
        return jsonify({"erro": f"Campos obrigatórios faltando: {', '.join(faltando)}"}), 400
    _, afetadas = executar(
        "UPDATE Cliente SET nome=%s, cpf=%s, telefone=%s, email=%s WHERE id_cliente=%s",
        (dados["nome"], dados["cpf"], dados.get("telefone"), dados.get("email"), id_cliente),
    )
    if afetadas == 0:
        return jsonify({"erro": "Cliente não encontrado"}), 404
    return jsonify({"ok": True})


@app.delete("/api/clientes/<int:id_cliente>")
def deletar_cliente(id_cliente):
    try:
        _, afetadas = executar("DELETE FROM Cliente WHERE id_cliente=%s", (id_cliente,))
        if afetadas == 0:
            return jsonify({"erro": "Cliente não encontrado"}), 404
        return jsonify({"ok": True})
    except ValueError:
        return jsonify({"erro": "Não é possível excluir: este cliente está associado a vendas ou aluguéis."}), 409


# ============================================================
#  PROPRIETÁRIOS
# ============================================================

@app.get("/api/proprietarios")
def listar_proprietarios():
    return jsonify(consultar(
        "SELECT id_proprietario, nome, cpf_cnpj, telefone, email FROM Proprietario ORDER BY id_proprietario DESC"
    ))


@app.post("/api/proprietarios")
def criar_proprietario():
    dados = request.get_json(force=True) or {}
    faltando = campo_obrigatorio_faltando(dados, ["nome", "cpf_cnpj"])
    if faltando:
        return jsonify({"erro": f"Campos obrigatórios faltando: {', '.join(faltando)}"}), 400
    try:
        novo_id, _ = executar(
            "INSERT INTO Proprietario (nome, cpf_cnpj, telefone, email) VALUES (%s,%s,%s,%s)",
            (dados["nome"], dados["cpf_cnpj"], dados.get("telefone"), dados.get("email")),
        )
        return jsonify({"id_proprietario": novo_id}), 201
    except ValueError as e:
        return jsonify({"erro": f"Erro de integridade (CPF/CNPJ duplicado?): {e}"}), 400


@app.put("/api/proprietarios/<int:id_proprietario>")
def atualizar_proprietario(id_proprietario):
    dados = request.get_json(force=True) or {}
    faltando = campo_obrigatorio_faltando(dados, ["nome", "cpf_cnpj"])
    if faltando:
        return jsonify({"erro": f"Campos obrigatórios faltando: {', '.join(faltando)}"}), 400
    _, afetadas = executar(
        "UPDATE Proprietario SET nome=%s, cpf_cnpj=%s, telefone=%s, email=%s WHERE id_proprietario=%s",
        (dados["nome"], dados["cpf_cnpj"], dados.get("telefone"), dados.get("email"), id_proprietario),
    )
    if afetadas == 0:
        return jsonify({"erro": "Proprietário não encontrado"}), 404
    return jsonify({"ok": True})


@app.delete("/api/proprietarios/<int:id_proprietario>")
def deletar_proprietario(id_proprietario):
    try:
        _, afetadas = executar("DELETE FROM Proprietario WHERE id_proprietario=%s", (id_proprietario,))
        if afetadas == 0:
            return jsonify({"erro": "Proprietário não encontrado"}), 404
        return jsonify({"ok": True})
    except ValueError:
        return jsonify({"erro": "Não é possível excluir: este proprietário possui imóveis cadastrados."}), 409


# ============================================================
#  CORRETORES
# ============================================================

@app.get("/api/corretores")
def listar_corretores():
    return jsonify(consultar(
        "SELECT id_corretor, nome, creci, telefone, email FROM Corretor ORDER BY id_corretor DESC"
    ))


@app.post("/api/corretores")
def criar_corretor():
    dados = request.get_json(force=True) or {}
    faltando = campo_obrigatorio_faltando(dados, ["nome", "creci"])
    if faltando:
        return jsonify({"erro": f"Campos obrigatórios faltando: {', '.join(faltando)}"}), 400
    try:
        novo_id, _ = executar(
            "INSERT INTO Corretor (nome, creci, telefone, email) VALUES (%s,%s,%s,%s)",
            (dados["nome"], dados["creci"], dados.get("telefone"), dados.get("email")),
        )
        return jsonify({"id_corretor": novo_id}), 201
    except ValueError as e:
        return jsonify({"erro": f"Erro de integridade (CRECI duplicado?): {e}"}), 400


@app.put("/api/corretores/<int:id_corretor>")
def atualizar_corretor(id_corretor):
    dados = request.get_json(force=True) or {}
    faltando = campo_obrigatorio_faltando(dados, ["nome", "creci"])
    if faltando:
        return jsonify({"erro": f"Campos obrigatórios faltando: {', '.join(faltando)}"}), 400
    _, afetadas = executar(
        "UPDATE Corretor SET nome=%s, creci=%s, telefone=%s, email=%s WHERE id_corretor=%s",
        (dados["nome"], dados["creci"], dados.get("telefone"), dados.get("email"), id_corretor),
    )
    if afetadas == 0:
        return jsonify({"erro": "Corretor não encontrado"}), 404
    return jsonify({"ok": True})


@app.delete("/api/corretores/<int:id_corretor>")
def deletar_corretor(id_corretor):
    try:
        _, afetadas = executar("DELETE FROM Corretor WHERE id_corretor=%s", (id_corretor,))
        if afetadas == 0:
            return jsonify({"erro": "Corretor não encontrado"}), 404
        return jsonify({"ok": True})
    except ValueError:
        return jsonify({"erro": "Não é possível excluir: este corretor possui vendas ou aluguéis vinculados."}), 409


# ============================================================
#  VENDAS
# ============================================================

@app.get("/api/vendas")
def listar_vendas():
    sql = """
    SELECT
        v.id_venda, v.id_cliente, c.nome AS cliente,
        v.id_corretor, co.nome AS corretor,
        v.id_imovel, v.data_venda, v.valor_venda
    FROM Venda v
    JOIN Cliente c ON v.id_cliente = c.id_cliente
    JOIN Corretor co ON v.id_corretor = co.id_corretor
    JOIN Imovel i ON v.id_imovel = i.id_imovel
    ORDER BY v.id_venda DESC
    """
    return jsonify(consultar(sql))


@app.post("/api/vendas")
def criar_venda():
    dados = request.get_json(force=True) or {}
    faltando = campo_obrigatorio_faltando(
        dados, ["id_cliente", "id_corretor", "id_imovel", "data_venda", "valor_venda"]
    )
    if faltando:
        return jsonify({"erro": f"Campos obrigatórios faltando: {', '.join(faltando)}"}), 400
    try:
        novo_id, _ = executar(
            """INSERT INTO Venda (id_cliente, id_corretor, id_imovel, data_venda, valor_venda)
               VALUES (%s,%s,%s,%s,%s)""",
            (dados["id_cliente"], dados["id_corretor"], dados["id_imovel"],
             dados["data_venda"], dados["valor_venda"]),
        )
        return jsonify({"id_venda": novo_id}), 201
    except ValueError as e:
        return jsonify({"erro": f"Erro de integridade: {e}"}), 400


@app.put("/api/vendas/<int:id_venda>")
def atualizar_venda(id_venda):
    dados = request.get_json(force=True) or {}
    faltando = campo_obrigatorio_faltando(
        dados, ["id_cliente", "id_corretor", "id_imovel", "data_venda", "valor_venda"]
    )
    if faltando:
        return jsonify({"erro": f"Campos obrigatórios faltando: {', '.join(faltando)}"}), 400
    _, afetadas = executar(
        """UPDATE Venda SET id_cliente=%s, id_corretor=%s, id_imovel=%s, data_venda=%s, valor_venda=%s
           WHERE id_venda=%s""",
        (dados["id_cliente"], dados["id_corretor"], dados["id_imovel"],
         dados["data_venda"], dados["valor_venda"], id_venda),
    )
    if afetadas == 0:
        return jsonify({"erro": "Venda não encontrada"}), 404
    return jsonify({"ok": True})


@app.delete("/api/vendas/<int:id_venda>")
def deletar_venda(id_venda):
    try:
        _, afetadas = executar("DELETE FROM Venda WHERE id_venda=%s", (id_venda,))
        if afetadas == 0:
            return jsonify({"erro": "Venda não encontrada"}), 404
        return jsonify({"ok": True})
    except ValueError:
        return jsonify({"erro": "Não é possível excluir: esta venda está associada a um contrato."}), 409


# ============================================================
#  ALUGUÉIS
# ============================================================

@app.get("/api/alugueis")
def listar_alugueis():
    sql = """
    SELECT
        a.id_aluguel, a.id_cliente, c.nome AS cliente,
        a.id_corretor, co.nome AS corretor,
        a.id_imovel, a.data_inicio, a.valor_aluguel
    FROM Aluguel a
    JOIN Cliente c ON a.id_cliente = c.id_cliente
    JOIN Corretor co ON a.id_corretor = co.id_corretor
    JOIN Imovel i ON a.id_imovel = i.id_imovel
    ORDER BY a.id_aluguel DESC
    """
    return jsonify(consultar(sql))


@app.post("/api/alugueis")
def criar_aluguel():
    dados = request.get_json(force=True) or {}
    faltando = campo_obrigatorio_faltando(
        dados, ["id_cliente", "id_corretor", "id_imovel", "data_inicio", "valor_aluguel"]
    )
    if faltando:
        return jsonify({"erro": f"Campos obrigatórios faltando: {', '.join(faltando)}"}), 400
    try:
        novo_id, _ = executar(
            """INSERT INTO Aluguel (id_cliente, id_corretor, id_imovel, data_inicio, valor_aluguel)
               VALUES (%s,%s,%s,%s,%s)""",
            (dados["id_cliente"], dados["id_corretor"], dados["id_imovel"],
             dados["data_inicio"], dados["valor_aluguel"]),
        )
        return jsonify({"id_aluguel": novo_id}), 201
    except ValueError as e:
        return jsonify({"erro": f"Erro de integridade: {e}"}), 400


@app.put("/api/alugueis/<int:id_aluguel>")
def atualizar_aluguel(id_aluguel):
    dados = request.get_json(force=True) or {}
    faltando = campo_obrigatorio_faltando(
        dados, ["id_cliente", "id_corretor", "id_imovel", "data_inicio", "valor_aluguel"]
    )
    if faltando:
        return jsonify({"erro": f"Campos obrigatórios faltando: {', '.join(faltando)}"}), 400
    _, afetadas = executar(
        """UPDATE Aluguel SET id_cliente=%s, id_corretor=%s, id_imovel=%s, data_inicio=%s, valor_aluguel=%s
           WHERE id_aluguel=%s""",
        (dados["id_cliente"], dados["id_corretor"], dados["id_imovel"],
         dados["data_inicio"], dados["valor_aluguel"], id_aluguel),
    )
    if afetadas == 0:
        return jsonify({"erro": "Aluguel não encontrado"}), 404
    return jsonify({"ok": True})


@app.delete("/api/alugueis/<int:id_aluguel>")
def deletar_aluguel(id_aluguel):
    try:
        _, afetadas = executar("DELETE FROM Aluguel WHERE id_aluguel=%s", (id_aluguel,))
        if afetadas == 0:
            return jsonify({"erro": "Aluguel não encontrado"}), 404
        return jsonify({"ok": True})
    except ValueError:
        return jsonify({"erro": "Não é possível excluir: este aluguel está associado a um contrato."}), 409


# ============================================================
#  CONTRATOS
# ============================================================

@app.get("/api/contratos")
def listar_contratos():
    return jsonify(consultar(
        """SELECT id_contrato, id_venda, id_aluguel, data_assinatura, data_inicio, data_fim, clausulas
           FROM Contrato ORDER BY id_contrato DESC"""
    ))


@app.post("/api/contratos")
def criar_contrato():
    dados = request.get_json(force=True) or {}
    if not dados.get("id_venda") and not dados.get("id_aluguel"):
        return jsonify({"erro": "Informe id_venda ou id_aluguel."}), 400
    faltando = campo_obrigatorio_faltando(dados, ["data_assinatura", "data_inicio"])
    if faltando:
        return jsonify({"erro": f"Campos obrigatórios faltando: {', '.join(faltando)}"}), 400
    try:
        novo_id, _ = executar(
            """INSERT INTO Contrato (id_venda, id_aluguel, data_assinatura, data_inicio, data_fim, clausulas)
               VALUES (%s,%s,%s,%s,%s,%s)""",
            (dados.get("id_venda"), dados.get("id_aluguel"), dados["data_assinatura"],
             dados["data_inicio"], dados.get("data_fim"), dados.get("clausulas")),
        )
        return jsonify({"id_contrato": novo_id}), 201
    except ValueError as e:
        return jsonify({"erro": f"Erro de integridade: {e}"}), 400


@app.put("/api/contratos/<int:id_contrato>")
def atualizar_contrato(id_contrato):
    dados = request.get_json(force=True) or {}
    if not dados.get("id_venda") and not dados.get("id_aluguel"):
        return jsonify({"erro": "Informe id_venda ou id_aluguel."}), 400
    faltando = campo_obrigatorio_faltando(dados, ["data_assinatura", "data_inicio"])
    if faltando:
        return jsonify({"erro": f"Campos obrigatórios faltando: {', '.join(faltando)}"}), 400
    _, afetadas = executar(
        """UPDATE Contrato SET id_venda=%s, id_aluguel=%s, data_assinatura=%s, data_inicio=%s,
           data_fim=%s, clausulas=%s WHERE id_contrato=%s""",
        (dados.get("id_venda"), dados.get("id_aluguel"), dados["data_assinatura"],
         dados["data_inicio"], dados.get("data_fim"), dados.get("clausulas"), id_contrato),
    )
    if afetadas == 0:
        return jsonify({"erro": "Contrato não encontrado"}), 404
    return jsonify({"ok": True})


@app.delete("/api/contratos/<int:id_contrato>")
def deletar_contrato(id_contrato):
    _, afetadas = executar("DELETE FROM Contrato WHERE id_contrato=%s", (id_contrato,))
    if afetadas == 0:
        return jsonify({"erro": "Contrato não encontrado"}), 404
    return jsonify({"ok": True})


# ============================================================
#  Arquivos estáticos
# ============================================================

@app.get("/")
def home():
    return send_from_directory(app.static_folder, "alleanza-painel-interno.html")


@app.get("/healthz")
def healthz():
    return jsonify({"status": "ok"})


if __name__ == "__main__":
    porta = int(os.getenv("PORT", 5000))
    app.run(host="0.0.0.0", port=porta)
