
from pathlib import Path
import os
import sqlite3
import uuid
import secrets
from datetime import datetime
from functools import wraps

from flask import (
    Flask, abort, flash, redirect, render_template_string,
    request, send_from_directory, session, url_for
)
from werkzeug.utils import secure_filename

BASE_DIR = Path(__file__).resolve().parent
UPLOAD_DIR = BASE_DIR / "uploads"
DB_PATH = BASE_DIR / "audios.db"
ALLOWED_EXTENSIONS = {"mp3", "wav", "m4a", "ogg", "opus", "aac", "flac", "webm", "mp4"}

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY") or secrets.token_hex(32)
app.config["MAX_CONTENT_LENGTH"] = 512 * 1024 * 1024
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["SESSION_COOKIE_SECURE"] = True
UPLOAD_DIR.mkdir(exist_ok=True)

def db():
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    return connection

def init_db():
    with db() as connection:
        connection.execute("""
            CREATE TABLE IF NOT EXISTS posts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                caption TEXT NOT NULL DEFAULT '',
                filename TEXT NOT NULL,
                likes INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
            )
        """)
        columns = {row["name"] for row in connection.execute("PRAGMA table_info(posts)")}
        if "is_deleted" not in columns:
            connection.execute("ALTER TABLE posts ADD COLUMN is_deleted INTEGER NOT NULL DEFAULT 0")
        connection.execute("""
            CREATE TABLE IF NOT EXISTS reports (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                post_id INTEGER NOT NULL,
                reason TEXT NOT NULL,
                created_at TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'Nova'
            )
        """)

init_db()

def csrf_token():
    if "csrf_token" not in session:
        session["csrf_token"] = secrets.token_urlsafe(32)
    return session["csrf_token"]

@app.context_processor
def inject_helpers():
    return {"csrf_token": csrf_token}

def verify_csrf():
    submitted = request.form.get("csrf_token", "")
    expected = session.get("csrf_token", "")
    if not expected or not secrets.compare_digest(submitted, expected):
        abort(400, "Solicitação inválida. Atualize a página e tente novamente.")

def admin_required(function):
    @wraps(function)
    def wrapper(*args, **kwargs):
        if not session.get("is_admin"):
            return redirect(url_for("admin_login"))
        return function(*args, **kwargs)
    return wrapper

def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS

PAGE = r"""
<!doctype html>
<html lang="pt-br">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Vox — Rede social de áudios</title>
<style>
:root{--bg:#100b1d;--panel:#1d1430;--panel2:#281b40;--purple:#a879ff;--pink:#e18cff;--text:#f7f1ff;--muted:#b9a9ce;--line:#3a2a52}
*{box-sizing:border-box} body{margin:0;background:radial-gradient(circle at 80% 0%,#38205b 0,transparent 35%),var(--bg);color:var(--text);font:16px system-ui,-apple-system,Segoe UI,sans-serif}
header{position:sticky;top:0;background:#100b1deF;backdrop-filter:blur(12px);border-bottom:1px solid var(--line);z-index:2}
nav{max-width:980px;margin:auto;padding:16px 20px;display:flex;align-items:center;justify-content:space-between}
.logo{font-size:25px;font-weight:850;letter-spacing:-1px}.logo span{color:var(--purple)}.tag{color:var(--muted);font-size:13px}
main{max-width:760px;margin:30px auto;padding:0 16px}
.hero{padding:26px;border:1px solid #594078;border-radius:24px;background:linear-gradient(135deg,#38205a,#201333 70%);margin-bottom:22px}
h1{font-size:clamp(26px,5vw,38px);line-height:1.1;margin:0 0 8px}.hero p{color:#d5c5e9;margin:0}
.card{background:var(--panel);border:1px solid var(--line);border-radius:20px;padding:20px;margin-bottom:16px;box-shadow:0 12px 35px #0002}
h2{font-size:19px;margin:0 0 14px}
textarea,input[type=text],input[type=password]{width:100%;background:#120d20;color:var(--text);border:1px solid var(--line);border-radius:12px;padding:12px;font:inherit}
textarea{min-height:76px;resize:vertical}
input[type=file]{display:block;width:100%;margin:12px 0;color:var(--muted)}
button,.button{border:0;border-radius:12px;padding:11px 16px;background:linear-gradient(120deg,var(--purple),var(--pink));color:#190d29;font-weight:750;font:inherit;cursor:pointer;text-decoration:none;display:inline-flex;align-items:center;justify-content:center}
button:disabled{opacity:.5;cursor:not-allowed}.secondary{background:var(--panel2);color:var(--text);border:1px solid var(--line)}
.danger{background:#8f3456;color:white}.restore{background:#276b50;color:white}
.actions{display:flex;gap:10px;flex-wrap:wrap;margin-top:12px}.hint,.muted{color:var(--muted);font-size:13px}
.status{min-height:22px;color:#e7c9ff;font-size:14px;margin:8px 0}
audio{width:100%;margin-top:10px;filter:hue-rotate(35deg)}
.post-head{display:flex;align-items:center;gap:10px;margin-bottom:12px}.avatar{width:40px;height:40px;border-radius:50%;display:grid;place-items:center;background:linear-gradient(135deg,#9b69ff,#e18cff);font-weight:800;color:#1a1028}
.post-title{font-weight:750}.post-date{font-size:12px;color:var(--muted)}
.like{background:#39234f;color:#f4dfff;border:1px solid #63417e}.flash{padding:12px 14px;border-radius:12px;background:#38234d;color:#f5dcff;margin-bottom:12px}
.rec-dot{display:inline-block;width:9px;height:9px;border-radius:50%;background:#ff5c85;margin-right:7px}
footer{text-align:center;color:var(--muted);font-size:12px;padding:24px}
@media(max-width:520px){main{margin:18px auto}.hero{padding:20px}.card{padding:16px}}
</style>
</head>
<body>
<header><nav><div class="logo">vox<span>.</span></div><div class="tag">uma rede feita de voz · <a href="{{ url_for('admin_login') }}" style="color:inherit">admin</a></div></nav></header>
<main>
<section class="hero"><h1>Menos texto.<br>Mais voz.</h1><p>Compartilhe suas ideias, histórias e momentos em áudio.</p></section>
{% with messages = get_flashed_messages() %}{% for message in messages %}<div class="flash">{{ message }}</div>{% endfor %}{% endwith %}
<section class="card">
<h2>Compartilhe sua voz</h2>
<form id="uploadForm" action="{{ url_for('publish') }}" method="post" enctype="multipart/form-data">
<input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
<label class="muted" for="caption">Título (opcional)</label>
<input id="caption" name="caption" type="text" maxlength="90" placeholder="Sobre o que é seu áudio?">
<label class="muted" for="audioFile">Escolha um áudio do dispositivo</label>
<input id="audioFile" name="audio" type="file" accept="audio/*,.webm,.mp4" required>
<div class="actions"><button type="submit">Publicar áudio</button></div>
<p class="hint">Formatos comuns: MP3, WAV, M4A, OGG e WebM.</p>
</form>
<hr style="border:0;border-top:1px solid var(--line);margin:18px 0">
<h2>Ou grave agora</h2>
<div class="actions"><button class="secondary" id="recordBtn" type="button">● Começar gravação</button><button class="secondary" id="stopBtn" type="button" disabled>Parar</button></div>
<div class="status" id="recordStatus">A gravação usa o microfone do navegador.</div>
<audio id="preview" controls hidden></audio>
<form id="recordForm" action="{{ url_for('publish') }}" method="post" enctype="multipart/form-data" hidden>
<input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
<input type="hidden" name="caption" value="Áudio gravado">
<input id="recordedFile" type="file" name="audio">
<button type="submit">Publicar gravação</button>
</form>
</section>
<h2 style="margin:26px 4px 14px">Feed público <span class="muted">· {{ posts|length }} áudio(s)</span></h2>
{% for post in posts %}
<article class="card">
<div class="post-head"><div class="avatar">V</div><div><div class="post-title">{{ post["caption"] or "Áudio sem título" }}</div><div class="post-date">Comunidade Vox · {{ post["created_at"] }}</div></div></div>
<audio controls preload="none" src="{{ url_for('uploaded_file', filename=post['filename']) }}">Seu navegador não suporta áudio.</audio>
<div class="actions">
<form action="{{ url_for('like', post_id=post['id']) }}" method="post"><input type="hidden" name="csrf_token" value="{{ csrf_token() }}"><button class="like" type="submit">♥ Curtir · {{ post["likes"] }}</button></form>
<form action="{{ url_for('report', post_id=post['id']) }}" method="post"><input type="hidden" name="csrf_token" value="{{ csrf_token() }}"><button class="secondary" type="submit">Denunciar</button></form>
</div>
</article>
{% else %}
<section class="card muted">Ainda não há publicações. Seja a primeira pessoa a compartilhar um áudio!</section>
{% endfor %}
</main>
<footer>VOX · uma rede feita de voz</footer>
<script>
let recorder, chunks = [];
const recordBtn = document.getElementById('recordBtn');
const stopBtn = document.getElementById('stopBtn');
const statusText = document.getElementById('recordStatus');
const preview = document.getElementById('preview');
const recordForm = document.getElementById('recordForm');
recordBtn.addEventListener('click', async () => {
  if (!navigator.mediaDevices || !window.MediaRecorder) {
    statusText.textContent = 'Este navegador não oferece gravação de áudio. Tente Chrome ou outro navegador atualizado.';
    return;
  }
  try {
    const stream = await navigator.mediaDevices.getUserMedia({audio:true});
    chunks = [];
    recorder = new MediaRecorder(stream);
    recorder.ondataavailable = e => { if (e.data.size) chunks.push(e.data); };
    recorder.onstop = () => {
      const blob = new Blob(chunks, {type: recorder.mimeType || 'audio/webm'});
      const ext = (blob.type.includes('mp4') ? 'mp4' : 'webm');
      const file = new File([blob], 'gravacao.' + ext, {type: blob.type});
      const transfer = new DataTransfer(); transfer.items.add(file);
      document.getElementById('recordedFile').files = transfer.files;
      preview.src = URL.createObjectURL(blob); preview.hidden = false;
      recordForm.hidden = false;
      stream.getTracks().forEach(track => track.stop());
      statusText.textContent = 'Gravação pronta. Ouça a prévia e publique quando quiser.';
    };
    recorder.start();
    recordBtn.disabled = true; stopBtn.disabled = false;
    statusText.innerHTML = '<span class="rec-dot"></span>Gravando…';
  } catch (err) {
    statusText.textContent = 'Não foi possível acessar o microfone. Verifique a permissão do navegador.';
  }
});
stopBtn.addEventListener('click', () => {
  if (recorder && recorder.state !== 'inactive') recorder.stop();
  recordBtn.disabled = false; stopBtn.disabled = true;
});
</script>
</body></html>
"""

LOGIN_PAGE = r"""
<!doctype html><html lang="pt-br"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Admin VOX</title>
<style>
body{margin:0;background:#100b1d;color:#f7f1ff;font:16px system-ui;padding:24px}
main{max-width:420px;margin:50px auto;background:#1d1430;border:1px solid #3a2a52;border-radius:20px;padding:24px}
input{width:100%;box-sizing:border-box;margin:8px 0 16px;padding:12px;border-radius:10px;border:1px solid #594078;background:#120d20;color:white}
button{padding:12px 18px;border:0;border-radius:10px;background:#a879ff;color:#190d29;font-weight:bold}
a{color:#d5baff}.flash{background:#38234d;padding:12px;border-radius:10px;margin-bottom:14px}
</style></head><body><main><h1>VOX · Administrador</h1>
{% with messages=get_flashed_messages() %}{% for message in messages %}<div class="flash">{{message}}</div>{% endfor %}{% endwith %}
<form method="post"><input type="hidden" name="csrf_token" value="{{csrf_token()}}">
<label>Usuário</label><input name="username" autocomplete="username" required>
<label>Senha</label><input type="password" name="password" autocomplete="current-password" required>
<button type="submit">Entrar</button></form><p><a href="{{url_for('home')}}">Voltar ao VOX</a></p></main></body></html>
"""

ADMIN_PAGE = r"""
<!doctype html><html lang="pt-br"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Painel VOX</title>
<style>
body{margin:0;background:#100b1d;color:#f7f1ff;font:16px system-ui;padding:18px}
main{max-width:760px;margin:auto}section{background:#1d1430;border:1px solid #3a2a52;border-radius:16px;padding:18px;margin:14px 0}
a{color:#d5baff}button{padding:10px 14px;border:0;border-radius:9px;background:#a879ff;color:#190d29;font-weight:bold}
.danger{background:#a94362;color:white}.restore{background:#327c5b;color:white}audio{width:100%;margin:10px 0}.muted{color:#b9a9ce}
</style></head><body><main><h1>VOX · Painel administrativo</h1><p><a href="{{url_for('home')}}">Ver feed</a> · <a href="{{url_for('admin_logout')}}">Sair</a></p>
<h2>Publicações ativas</h2>
{% for post in active %}<section><b>{{post["caption"] or "Áudio sem título"}}</b><p class="muted">Publicação #{{post["id"]}} · {{post["created_at"]}}</p><audio controls src="{{url_for('uploaded_file',filename=post['filename'])}}"></audio>
<form method="post" action="{{url_for('trash_post',post_id=post['id'])}}"><input type="hidden" name="csrf_token" value="{{csrf_token()}}"><button class="danger">Mover para lixeira</button></form></section>
{% else %}<p class="muted">Nenhuma publicação ativa.</p>{% endfor %}
<h2>Lixeira privada</h2>
{% for post in deleted %}<section><b>{{post["caption"] or "Áudio sem título"}}</b><p class="muted">Publicação #{{post["id"]}}</p>
<form method="post" action="{{url_for('restore_post',post_id=post['id'])}}"><input type="hidden" name="csrf_token" value="{{csrf_token()}}"><button class="restore">Restaurar publicação</button></form></section>
{% else %}<p class="muted">A lixeira está vazia.</p>{% endfor %}
<h2>Denúncias recebidas</h2>
{% for report_item in reports %}<section><b>Publicação #{{report_item["post_id"]}}</b><p>{{report_item["reason"]}}</p><p class="muted">{{report_item["created_at"]}} · {{report_item["status"]}}</p>
<form method="post" action="{{url_for('resolve_report',report_id=report_item['id'])}}"><input type="hidden" name="csrf_token" value="{{csrf_token()}}"><button>Marcar como analisada</button></form></section>
{% else %}<p class="muted">Nenhuma denúncia recebida.</p>{% endfor %}
</main></body></html>
"""

@app.get("/")
def home():
    with db() as connection:
        posts = connection.execute(
            "SELECT * FROM posts WHERE COALESCE(is_deleted, 0)=0 ORDER BY id DESC"
        ).fetchall()
    return render_template_string(PAGE, posts=posts)

@app.post("/publish")
def publish():
    verify_csrf()
    uploaded = request.files.get("audio")
    if not uploaded or not uploaded.filename:
        flash("Escolha um arquivo de áudio antes de publicar.")
        return redirect(url_for("home"))
    safe_name = secure_filename(uploaded.filename)
    if not allowed_file(safe_name):
        flash("Formato não aceito. Envie um arquivo de áudio compatível.")
        return redirect(url_for("home"))
    extension = safe_name.rsplit(".", 1)[1].lower()
    stored_name = f"{uuid.uuid4().hex}.{extension}"
    uploaded.save(UPLOAD_DIR / stored_name)
    caption = request.form.get("caption", "").strip()[:90]
    with db() as connection:
        connection.execute(
            "INSERT INTO posts (caption, filename) VALUES (?, ?)",
            (caption, stored_name)
        )
    flash("Seu áudio foi publicado no feed!")
    return redirect(url_for("home"))

@app.post("/like/<int:post_id>")
def like(post_id):
    verify_csrf()
    with db() as connection:
        cursor = connection.execute(
            "UPDATE posts SET likes = likes + 1 WHERE id = ? AND COALESCE(is_deleted,0)=0",
            (post_id,)
        )
        if cursor.rowcount == 0:
            abort(404)
    return redirect(url_for("home"))

@app.post("/denunciar/<int:post_id>")
def report(post_id):
    verify_csrf()
    with db() as connection:
        exists = connection.execute(
            "SELECT id FROM posts WHERE id=? AND COALESCE(is_deleted,0)=0", (post_id,)
        ).fetchone()
        if exists:
            connection.execute(
                "INSERT INTO reports (post_id, reason, created_at) VALUES (?, ?, ?)",
                (post_id, "Conteúdo denunciado por um usuário", datetime.now().strftime("%d/%m/%Y %H:%M"))
            )
    flash("Denúncia enviada para análise.")
    return redirect(url_for("home"))

@app.get("/uploads/<path:filename>")
def uploaded_file(filename):
    return send_from_directory(UPLOAD_DIR, filename, as_attachment=False)

@app.route("/admin", methods=["GET", "POST"])
def admin_login():
    if session.get("is_admin"):
        return redirect(url_for("admin_panel"))
    if request.method == "POST":
        verify_csrf()
        configured_username = os.environ.get("ADMIN_USERNAME", "")
        configured_password = os.environ.get("ADMIN_PASSWORD", "")
        entered_username = request.form.get("username", "")
        entered_password = request.form.get("password", "")
        if (configured_username and configured_password
            and secrets.compare_digest(entered_username, configured_username)
            and secrets.compare_digest(entered_password, configured_password)):
            session.clear()
            session["is_admin"] = True
            session["csrf_token"] = secrets.token_urlsafe(32)
            return redirect(url_for("admin_panel"))
        flash("Usuário ou senha incorretos, ou variáveis do administrador não configuradas no Render.")
    return render_template_string(LOGIN_PAGE)

@app.get("/admin/painel")
@admin_required
def admin_panel():
    with db() as connection:
        active = connection.execute(
            "SELECT * FROM posts WHERE COALESCE(is_deleted,0)=0 ORDER BY id DESC"
        ).fetchall()
        deleted = connection.execute(
            "SELECT * FROM posts WHERE COALESCE(is_deleted,0)=1 ORDER BY id DESC"
        ).fetchall()
        reports = connection.execute("SELECT * FROM reports ORDER BY id DESC").fetchall()
    return render_template_string(ADMIN_PAGE, active=active, deleted=deleted, reports=reports)

@app.post("/admin/lixeira/<int:post_id>")
@admin_required
def trash_post(post_id):
    verify_csrf()
    with db() as connection:
        connection.execute("UPDATE posts SET is_deleted=1 WHERE id=?", (post_id,))
    flash("Publicação movida para a lixeira.")
    return redirect(url_for("admin_panel"))

@app.post("/admin/restaurar/<int:post_id>")
@admin_required
def restore_post(post_id):
    verify_csrf()
    with db() as connection:
        connection.execute("UPDATE posts SET is_deleted=0 WHERE id=?", (post_id,))
    flash("Publicação restaurada.")
    return redirect(url_for("admin_panel"))

@app.post("/admin/denuncia/<int:report_id>")
@admin_required
def resolve_report(report_id):
    verify_csrf()
    with db() as connection:
        connection.execute("UPDATE reports SET status='Analisada' WHERE id=?", (report_id,))
    return redirect(url_for("admin_panel"))

@app.get("/admin/sair")
def admin_logout():
    session.clear()
    return redirect(url_for("home"))

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=False)
