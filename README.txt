
import os
import uuid
from flask import Flask, request, redirect, url_for, render_template_string, flash
from supabase import create_client

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "troque-esta-chave")

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
BUCKET = "audios"

supabase = None

if SUPABASE_URL and SUPABASE_KEY:
    supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

HTML = """
<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>VOX — Sua voz tem espaço</title>
<style>
* { box-sizing: border-box; }
body {
    margin: 0;
    background: #100b1c;
    color: white;
    font-family: Arial, sans-serif;
}
header {
    padding: 22px;
    background: #211039;
    border-bottom: 1px solid #563080;
}
.logo {
    color: #c69aff;
    font-size: 30px;
    font-weight: bold;
    letter-spacing: 4px;
}
header p { color: #c7b5d9; margin-bottom: 0; }
main { max-width: 650px; margin: auto; padding: 20px; }
.card {
    background: #21172e;
    border: 1px solid #49305e;
    border-radius: 16px;
    padding: 20px;
    margin-bottom: 18px;
}
h2 { color: #d1a8ff; }
input, button {
    width: 100%;
    padding: 13px;
    margin-top: 12px;
    border-radius: 9px;
    border: none;
}
input { background: #352544; color: white; }
button {
    background: #914ee8;
    color: white;
    font-weight: bold;
    cursor: pointer;
}
button:hover { background: #aa70f3; }
.post {
    background: #2a1d3a;
    padding: 17px;
    border-radius: 13px;
    margin: 14px 0;
}
.post small { color: #bca4d1; }
audio { width: 100%; margin-top: 12px; }
.notice { color: #d1b5ef; }
</style>
</head>
<body>
<header>
    <div class="logo">VOX</div>
    <p>Sua voz tem espaço.</p>
</header>
<main>
    <section class="card">
        <h2>Compartilhe sua voz</h2>
        <form action="/publicar" method="POST" enctype="multipart/form-data">
            <input name="nome" placeholder="Seu nome de exibição" maxlength="40" required>
            <input name="audio" type="file" accept="audio/*" required>
            <button type="submit">Enviar áudio</button>
        </form>
        <p class="notice">As publicações passam por aprovação antes de aparecer no feed.</p>
    </section>

    <section class="card">
        <h2>Feed do VOX</h2>
        {% for post in posts %}
        <div class="post">
            <strong>{{ post.nome }}</strong>
            <br>
            <small>Publicação de áudio</small>
            <audio controls preload="none">
                <source src="{{ post.audio_url }}">
            </audio>
        </div>
        {% else %}
        <p class="notice">Ainda não há publicações aprovadas. Seja paciente: o VOX está começando!</p>
        {% endfor %}
    </section>
</main>
</body>
</html>
"""

@app.route("/")
def inicio():
    posts = []

    if supabase:
        try:
            resultado = (
                supabase.table("posts")
                .select("nome,audio_url")
                .eq("status", "approved")
                .order("created_at", desc=True)
                .execute()
            )
            posts = resultado.data or []
        except Exception:
            posts = []

    return render_template_string(HTML, posts=posts)


@app.route("/publicar", methods=["POST"])
def publicar():
    if not supabase:
        return "Configuração do Supabase ausente.", 503

    nome = request.form.get("nome", "").strip()
    arquivo = request.files.get("audio")

    if not nome or not arquivo or not arquivo.filename:
        return "Preencha seu nome e escolha um áudio.", 400

    extensao = arquivo.filename.rsplit(".", 1)[-1].lower()

    if extensao not in {"mp3", "wav", "ogg", "m4a", "aac"}:
        return "Formato de áudio não permitido.", 400

    conteudo = arquivo.read()

    if len(conteudo) > 25 * 1024 * 1024:
        return "O arquivo ultrapassa o limite de 25 MB.", 413

    if not conteudo:
        return "O arquivo está vazio.", 400

    nome_arquivo = f"{uuid.uuid4()}.{extensao}"

    try:
        supabase.storage.from_(BUCKET).upload(
            nome_arquivo,
            conteudo,
            {"content-type": arquivo.mimetype or "application/octet-stream"}
        )

        url = supabase.storage.from_(BUCKET).get_public_url(nome_arquivo)

        supabase.table("posts").insert({
            "nome": nome[:40],
            "audio_url": url,
            "status": "pending"
        }).execute()

        return redirect(url_for("inicio"))

    except Exception:
        return "Não foi possível publicar. Confira a configuração do Supabase.", 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5000)))

