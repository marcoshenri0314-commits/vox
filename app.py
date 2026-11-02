import os
import uuid
import mimetypes
from functools import wraps
from datetime import datetime, timezone

from flask import (
    Flask, request, redirect, url_for, session,
    flash, render_template_string, abort
)
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from supabase import create_client, Client

# =========================================================
# CONFIGURAÇÃO
# =========================================================

app = Flask(__name__)
app.secret_key = os.environ["FLASK_SECRET_KEY"]
app.config["MAX_CONTENT_LENGTH"] = 512 * 1024 * 1024
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["SESSION_COOKIE_SECURE"] = True

SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_KEY = os.environ["SUPABASE_SERVICE_ROLE_KEY"]

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

BUCKET = os.environ.get("SUPABASE_BUCKET", "vox-audios")

AUDIO_EXTENSIONS = {"mp3", "wav", "m4a", "ogg", "opus", "aac", "flac", "webm"}
IMAGE_EXTENSIONS = {"jpg", "jpeg", "png", "webp"}

# =========================================================
# FUNÇÕES AUXILIARES
# =========================================================

def extension(filename):
    return filename.rsplit(".", 1)[-1].lower() if "." in filename else ""

def current_user():
    user_id = session.get("user_id")
    if not user_id:
        return None
    result = supabase.table("profiles").select("*").eq("id", user_id).limit(1).execute()
    return result.data[0] if result.data else None

def login_required(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        if not session.get("user_id"):
            return redirect(url_for("login"))
        return func(*args, **kwargs)
    return wrapper

def admin_required(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        user = current_user()
        if not user or not user.get("is_admin"):
            abort(403)
        return func(*args, **kwargs)
    return wrapper

def upload_file(file, allowed):
    if not file or not file.filename:
        raise ValueError("Selecione um arquivo.")

    ext = extension(file.filename)
    if ext not in allowed:
        raise ValueError("Formato de arquivo não permitido.")

    name = f"{uuid.uuid4().hex}.{ext}"
    content = file.read()

    if not content:
        raise ValueError("Arquivo vazio.")

    content_type = file.mimetype or mimetypes.guess_type(name)[0] or "application/octet-stream"

    supabase.storage.from_(BUCKET).upload(
        name,
        content,
        {"content-type": content_type}
    )

    return name

def media_url(filename):
    if not filename:
        return ""
    result = supabase.storage.from_(BUCKET).create_signed_url(filename, 3600)
    return result.get("signedURL", "")

def profile_by_id(user_id):
    result = supabase.table("profiles").select("*").eq("id", user_id).limit(1).execute()
    return result.data[0] if result.data else None

def render_page(content, **kwargs):
    user = current_user()
    return render_template_string(
        BASE_HTML,
        content=content,
        user=user,
        **kwargs
    )

# =========================================================
# INTERFACE
# =========================================================

BASE_HTML = """
<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>VOX — Sua voz, sua rede. 💜</title>
<style>
*{box-sizing:border-box}
body{margin:0;background:#100d18;color:#fff;font-family:Arial,sans-serif}
header{background:#1c1528;padding:18px;display:flex;justify-content:space-between;
align-items:center;position:sticky;top:0;z-index:5}
.logo{font-size:27px;font-weight:bold;color:#bd8aff}
header a, a{color:#c99cff;text-decoration:none}
main{max-width:650px;margin:25px auto;padding:0 14px}
.card{background:#211a2e;border:1px solid #38294c;border-radius:16px;
padding:17px;margin-bottom:17px}
input,textarea,button{width:100%;padding:13px;border-radius:9px;
border:1px solid #514064;background:#171220;color:white;margin:7px 0}
button{background:#8b45d6;border:0;font-weight:bold;cursor:pointer}
button:hover{background:#a765ed}
img.post{width:100%;border-radius:12px;margin-top:10px}
audio{width:100%;margin-top:10px}
small{color:#b9a9c9}
.actions{display:flex;gap:10px}
.actions form{flex:1}
.actions button{margin-bottom:0}
.avatar{width:55px;height:55px;object-fit:cover;border-radius:50%;
background:#39264f}
.posthead{display:flex;gap:12px;align-items:center}
h2{color:#d4b2ff}
</style>
</head>
<body>
<header>
<div class="logo">vox.</div>
<div>Sua voz, sua rede. 💜</div>
<nav>
{% if user %}
<a href="/">Início</a> ·
<a href="/perfil/{{ user.username }}">Perfil</a> ·
{% if user.is_admin %}<a href="/admin">Admin</a> ·{% endif %}
<a href="/sair">Sair</a>
{% else %}
<a href="/login">Entrar</a>
{% endif %}
</nav>
</header>
<main>
{% with messages = get_flashed_messages() %}
{% for message in messages %}
<div class="card">{{ message }}</div>
{% endfor %}
{% endwith %}
{{ content|safe }}
</main>
</body>
</html>
"""

# =========================================================
# CADASTRO E LOGIN
# =========================================================

@app.route("/cadastro", methods=["GET", "POST"])
def cadastro():
    if request.method == "POST":
        username = request.form.get("username", "").strip().lower().replace("@", "")
        display_name = request.form.get("display_name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        if not username or not email or len(password) < 8:
            flash("Preencha os dados. A senha precisa ter pelo menos 8 caracteres.")
            return redirect(url_for("cadastro"))

        if not username.replace("_", "").isalnum():
            flash("Use apenas letras, números e underline no usuário.")
            return redirect(url_for("cadastro"))

        existing = supabase.table("profiles").select("id").eq("username", username).execute()
        if existing.data:
            flash("Esse nome de usuário já está em uso.")
            return redirect(url_for("cadastro"))

        try:
            auth = supabase.auth.sign_up({
                "email": email,
                "password": password
            })

            if not auth.user:
                flash("Não foi possível criar a conta.")
                return redirect(url_for("cadastro"))

            supabase.table("profiles").insert({
                "id": auth.user.id,
                "username": username,
                "display_name": display_name or username,
                "bio": "",
                "avatar": None,
                "is_admin": False
            }).execute()

            flash("Conta criada! Confirme seu e-mail, se solicitado, e entre.")
            return redirect(url_for("login"))

        except Exception:
            flash("Não foi possível criar a conta. Verifique os dados.")
            return redirect(url_for("cadastro"))

    content = """
    <div class="card">
    <h2>Criar conta</h2>
    <form method="POST">
    <input name="display_name" placeholder="Seu nome">
    <input name="username" placeholder="Nome de usuário (sem @)" required>
    <input name="email" type="email" placeholder="E-mail" required>
    <input name="password" type="password" placeholder="Senha (mínimo 8 caracteres)" required>
    <button>Criar minha conta</button>
    </form>
    <a href="/login">Já tenho uma conta</a>
    </div>
    """
    return render_page(content)

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        try:
            result = supabase.auth.sign_in_with_password({
                "email": email,
                "password": password
            })

            if result.user:
                session.clear()
                session["user_id"] = result.user.id
                session["access_token"] = result.session.access_token
                return redirect(url_for("index"))

        except Exception:
            pass

        flash("E-mail ou senha incorretos.")

    content = """
    <div class="card">
    <h2>Entrar no VOX</h2>
    <form method="POST">
    <input name="email" type="email" placeholder="E-mail" required>
    <input name="password" type="password" placeholder="Senha" required>
    <button>Entrar</button>
    </form>
    <a href="/cadastro">Criar conta</a>
    </div>
    """
    return render_page(content)

@app.route("/sair")
def sair():
    session.clear()
    return redirect(url_for("login"))

# =========================================================
# FEED E PUBLICAÇÕES
# =========================================================

@app.route("/")
def index():
    posts = supabase.table("posts").select(
        "*, profiles(username, display_name, avatar)"
    ).eq("is_deleted", False).order("created_at", desc=True).limit(100).execute()

    content = """
    <div class="card">
    <h2>VOX</h2>
    <p>Menos texto. Mais voz.</p>
    {% if user %}
    <form action="/publicar" method="POST" enctype="multipart/form-data">
    <textarea name="caption" placeholder="Compartilhe uma ideia..."></textarea>
    <label>Áudio</label>
    <input type="file" name="audio" accept="audio/*">
    <label>Foto</label>
    <input type="file" name="photo" accept="image/jpeg,image/png,image/webp">
    <button>Publicar</button>
    </form>
    {% else %}
    <a href="/login">Entre para publicar</a>
    {% endif %}
    </div>
    """

    for post in posts.data:
        profile = post.get("profiles") or {}
        username = profile.get("username", "usuario")
        content += f"""
        <div class="card">
        <div class="posthead">
        <div>
        <b><a href="/perfil/{username}">{profile.get('display_name') or username}</a></b><br>
        <small>@{username}</small>
        </div></div>
        <p>{post.get('caption') or ''}</p>
        """

        if post.get("photo"):
            content += f'<img class="post" src="{media_url(post["photo"])}">'

        if post.get("audio"):
            content += f'<audio controls src="{media_url(post["audio"])}"></audio>'

        content += f"""
        <div class="actions">
        <form action="/curtir/{post['id']}" method="POST">
        <button>💜 Curtir</button></form>
        <form action="/denunciar/{post['id']}" method="POST">
        <button>⚑ Denunciar</button></form>
        </div>
        <a href="/post/{post['id']}">Comentários</a>
        </div>
        """

    return render_page(content)

@app.route("/publicar", methods=["POST"])
@login_required
def publicar():
    try:
        audio = request.files.get("audio")
        photo = request.files.get("photo")

        audio_name = upload_file(audio, AUDIO_EXTENSIONS) if audio and audio.filename else None
        photo_name = upload_file(photo, IMAGE_EXTENSIONS) if photo and photo.filename else None

        if not audio_name and not photo_name:
            flash("Envie um áudio ou uma foto.")
            return redirect(url_for("index"))

        supabase.table("posts").insert({
            "user_id": session["user_id"],
            "caption": request.form.get("caption", "")[:2000],
            "audio": audio_name,
            "photo": photo_name,
            "is_deleted": False
        }).execute()

        flash("Publicação enviada!")
    except Exception as error:
        flash("Não foi possível publicar. Verifique o arquivo e tente novamente.")

    return redirect(url_for("index"))

# =========================================================
# CURTIDAS E DENÚNCIAS
# =========================================================

@app.route("/curtir/<post_id>", methods=["POST"])
@login_required
def curtir(post_id):
    user_id = session["user_id"]
    existing = supabase.table("likes").select("id").eq(
        "post_id", post_id
    ).eq("user_id", user_id).execute()

    if existing.data:
        supabase.table("likes").delete().eq("post_id", post_id).eq(
            "user_id", user_id
        ).execute()
    else:
        supabase.table("likes").insert({
            "post_id": post_id,
            "user_id": user_id
        }).execute()

    return redirect(request.referrer or url_for("index"))

@app.route("/denunciar/<post_id>", methods=["POST"])
@login_required
def denunciar(post_id):
    supabase.table("reports").insert({
        "post_id": post_id,
        "reporter_id": session["user_id"],
        "reason": "Denúncia enviada pelo usuário",
        "resolved": False
    }).execute()

    flash("Denúncia enviada para análise.")
    return redirect(request.referrer or url_for("index"))

# =========================================================
# PERFIS
# =========================================================

@app.route("/perfil/<username>")
def perfil(username):
    result = supabase.table("profiles").select("*").eq(
        "username", username
    ).limit(1).execute()

    if not result.data:
        abort(404)

    profile = result.data[0]

    posts = supabase.table("posts").select("*").eq(
        "user_id", profile["id"]
    ).eq("is_deleted", False).order("created_at", desc=True).execute()

    followers = supabase.table("follows").select(
        "id", count="exact"
    ).eq("following_id", profile["id"]).execute()

    following = supabase.table("follows").select(
        "id", count="exact"
    ).eq("follower_id", profile["id"]).execute()

    content = f"""
    <div class="card">
    <h2>{profile.get('display_name') or username}</h2>
    <p>@{username}</p>
    <p>{profile.get('bio') or ''}</p>
    <p>Seguidores: {followers.count or 0} · Seguindo: {following.count or 0}</p>
    """

    if session.get("user_id") and session["user_id"] != profile["id"]:
        content += f"""
        <form action="/seguir/{profile['id']}" method="POST">
        <button>Seguir / Deixar de seguir</button>
        </form>
        """

    content += "</div><h2>Publicações</h2>"

    for post in posts.data:
        content += f'<div class="card"><p>{post.get("caption") or ""}</p>'
        if post.get("photo"):
            content += f'<img class="post" src="{media_url(post["photo"])}">'
        if post.get("audio"):
            content += f'<audio controls src="{media_url(post["audio"])}"></audio>'
        content += "</div>"

    return render_page(content)

@app.route("/perfil/editar", methods=["GET", "POST"])
@login_required
def editar_perfil():
    user = current_user()

    if request.method == "POST":
        username = request.form.get("username", "").strip().lower().replace("@", "")
        display_name = request.form.get("display_name", "").strip()
        bio = request.form.get("bio", "")[:500]

        existing = supabase.table("profiles").select("id").eq(
            "username", username
        ).neq("id", session["user_id"]).execute()

        if existing.data:
            flash("Esse @ já está sendo usado.")
            return redirect(url_for("editar_perfil"))

        supabase.table("profiles").update({
            "username": username,
            "display_name": display_name,
            "bio": bio
        }).eq("id", session["user_id"]).execute()

        avatar = request.files.get("avatar")
        if avatar and avatar.filename:
            avatar_name = upload_file(avatar, IMAGE_EXTENSIONS)
            supabase.table("profiles").update({
                "avatar": avatar_name
            }).eq("id", session["user_id"]).execute()

        flash("Perfil atualizado!")
        return redirect(url_for("perfil", username=username))

    content = f"""
    <div class="card">
    <h2>Editar perfil</h2>
    <form method="POST" enctype="multipart/form-data">
    <input name="display_name" value="{user.get('display_name') or ''}" placeholder="Nome">
    <input name="username" value="{user.get('username') or ''}" placeholder="@usuário">
    <textarea name="bio" placeholder="Biografia">{user.get('bio') or ''}</textarea>
    <label>Foto de perfil</label>
    <input type="file" name="avatar" accept="image/*">
    <button>Salvar alterações</button>
    </form>
    </div>
    """
    return render_page(content)

# =========================================================
# SEGUIDORES
# =========================================================

@app.route("/seguir/<user_id>", methods=["POST"])
@login_required
def seguir(user_id):
    follower = session["user_id"]

    if follower == user_id:
        abort(400)

    existing = supabase.table("follows").select("id").eq(
        "follower_id", follower
    ).eq("following_id", user_id).execute()

    if existing.data:
        supabase.table("follows").delete().eq(
            "follower_id", follower
        ).eq("following_id", user_id).execute()
    else:
        supabase.table("follows").insert({
            "follower_id": follower,
            "following_id": user_id
        }).execute()

    profile = profile_by_id(user_id)
    if profile:
        return redirect(url_for("perfil", username=profile["username"]))
    return redirect(url_for("index"))

# =========================================================
# COMENTÁRIOS POR ÁUDIO
# =========================================================

@app.route("/post/<post_id>")
def ver_post(post_id):
    result = supabase.table("posts").select("*").eq(
        "id", post_id
    ).eq("is_deleted", False).limit(1).execute()

    if not result.data:
        abort(404)

    post = result.data[0]
    comments = supabase.table("comments").select(
        "*, profiles(username, display_name)"
    ).eq("post_id", post_id).order("created_at").execute()

    content = f"""
    <div class="card">
    <p>{post.get('caption') or ''}</p>
    """

    if post.get("photo"):
        content += f'<img class="post" src="{media_url(post["photo"])}">'

    if post.get("audio"):
        content += f'<audio controls src="{media_url(post["audio"])}"></audio>'

    content += "</div><h2>Comentários em áudio</h2>"

    if session.get("user_id"):
        content += f"""
        <div class="card">
        <form action="/comentar/{post_id}" method="POST" enctype="multipart/form-data">
        <input type="file" name="audio" accept="audio/*" required>
        <button>Enviar comentário em áudio</button>
        </form>
        </div>
        """

    for comment in comments.data:
        profile = comment.get("profiles") or {}
        content += f"""
        <div class="card">
        <b>@{profile.get('username', 'usuario')}</b>
        <audio controls src="{media_url(comment['audio'])}"></audio>
        """

        if session.get("user_id"):
            content += f"""
            <form action="/responder/{comment['id']}" method="POST" enctype="multipart/form-data">
            <input type="file" name="audio" accept="audio/*" required>
            <button>Responder com áudio</button>
            </form>
            """

        replies = supabase.table("replies").select(
            "*, profiles(username)"
        ).eq("comment_id", comment["id"]).order("created_at").execute()

        for reply in replies.data:
            reply_profile = reply.get("profiles") or {}
            content += f"""
            <div class="card">
            <small>↳ @{reply_profile.get('username', 'usuario')}</small>
            <audio controls src="{media_url(reply['audio'])}"></audio>
            </div>
            """

        content += "</div>"

    return render_page(content)

@app.route("/comentar/<post_id>", methods=["POST"])
@login_required
def comentar(post_id):
    audio = request.files.get("audio")
    try:
        name = upload_file(audio, AUDIO_EXTENSIONS)
        supabase.table("comments").insert({
            "post_id": post_id,
            "user_id": session["user_id"],
            "audio": name
        }).execute()
except 
