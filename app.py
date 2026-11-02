
import os
import re
import uuid
import secrets
from datetime import datetime, timezone
from functools import wraps
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from flask import (
    Flask, request, redirect, url_for, session,
    flash, render_template_string, abort, jsonify
)
from supabase import create_client

app = Flask(__name__)

app.secret_key = os.environ.get("SECRET_KEY")
if not app.secret_key:
    raise RuntimeError("Configure SECRET_KEY no Render.")

app.config["MAX_CONTENT_LENGTH"] = 60 * 1024 * 1024
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SECURE"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"

SUPABASE_URL = os.environ.get("SUPABASE_URL", "").strip()
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "").strip()
ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "").strip().lower()

if not SUPABASE_URL or not SUPABASE_KEY:
    raise RuntimeError("Configure as chaves do Supabase no Render.")

sb = create_client(SUPABASE_URL, SUPABASE_KEY)

BUCKET = "vox-audios"
MAX_FILE_SIZE = 50 * 1024 * 1024

AUDIO_EXT = {
    "mp3", "wav", "m4a", "ogg", "opus",
    "aac", "flac", "webm", "mp4"
}

IMAGE_EXT = {"jpg", "jpeg", "png", "webp"}

def utcnow():
    return datetime.now(timezone.utc).isoformat()

def current_user():
    return session.get("user")

def current_user_id():
    user = current_user()
    return user.get("id") if user else None

def get_profile(user_id):
    if not user_id:
        return None

    result = (
        sb.table("profiles")
        .select("*")
        .eq("id", user_id)
        .maybe_single()
        .execute()
    )
    return result.data

def get_post(post_id):
    result = (
        sb.table("posts")
        .select("*")
        .eq("id", post_id)
        .maybe_single()
        .execute()
    )
    return result.data

def is_admin():
    profile = get_profile(current_user_id())
    return bool(profile and profile.get("is_admin"))

def allowed_file(filename, extensions):
    if not filename or "." not in filename:
        return False

    extension = filename.rsplit(".", 1)[1].lower()
    return extension in extensions

def new_storage_path(filename):
    extension = filename.rsplit(".", 1)[1].lower()
    return f"{uuid.uuid4().hex}.{extension}"

def login_required(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        if not current_user_id():
            flash("Faça login para continuar.")
            return redirect(url_for("login"))
        return func(*args, **kwargs)
    return wrapper


def admin_required(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        if not current_user_id():
            return redirect(url_for("login"))

        if not is_admin():
            abort(403)

        return func(*args, **kwargs)
    return wrapper


def valid_email(email):
    return bool(
        re.fullmatch(
            r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}",
            email
        )
    )


def valid_username(username):
    return bool(
        re.fullmatch(r"[a-zA-Z0-9_]{3,20}", username)
    )


@app.route("/cadastro", methods=["GET", "POST"])
def cadastro():
    if request.method == "POST":
        nome = request.form.get("nome", "").strip()
        username = request.form.get("username", "").strip().lower()
        email = request.form.get("email", "").strip().lower()
        senha = request.form.get("senha", "")

        if not nome or len(nome) > 60:
            flash("Informe um nome válido.")
            return redirect(url_for("cadastro"))

        if not valid_username(username):
            flash("O @ deve ter de 3 a 20 caracteres.")
            return redirect(url_for("cadastro"))

        if not valid_email(email):
            flash("E-mail inválido.")
            return redirect(url_for("cadastro"))

        if len(senha) < 8:
            flash("A senha precisa ter pelo menos 8 caracteres.")
            return redirect(url_for("cadastro"))

        existente = (
            sb.table("profiles")
            .select("id")
            .eq("username", username)
            .limit(1)
            .execute()
        )

        if existente.data:
            flash("Esse nome de usuário já está em uso.")
            return redirect(url_for("cadastro"))

        senha_hash = generate_password_hash(senha)

        resultado = sb.table("profiles").insert({
            "id": str(uuid.uuid4()),
            "name": nome,
            "username": username,
            "email": email,
            "password_hash": senha_hash,
            "bio": "",
            "avatar_url": None,
            "is_admin": email == ADMIN_EMAIL
        }).execute()

        if not resultado.data:
            flash("Não foi possível criar a conta.")
            return redirect(url_for("cadastro"))

        flash("Conta criada! Agora faça login.")
        return redirect(url_for("login"))

    return render_template_string("""
    <h1>Criar conta no VOX 💜</h1>
    <form method="POST">
      <input name="nome" placeholder="Seu nome" required>
      <input name="username" placeholder="Seu @usuário" required>
      <input name="email" type="email" placeholder="E-mail" required>
      <input name="senha" type="password" placeholder="Senha" required>
      <button type="submit">Criar conta</button>
    </form>
    <a href="/login">Já tenho conta</a>
    """)


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        senha = request.form.get("senha", "")

        resultado = (
            sb.table("profiles")
            .select("*")
            .eq("email", email)
            .limit(1)
            .execute()
        )

        if not resultado.data:
            flash("E-mail ou senha incorretos.")
            return redirect(url_for("login"))

        perfil = resultado.data[0]

        if not check_password_hash(
            perfil.get("password_hash", ""),
            senha
        ):
            flash("E-mail ou senha incorretos.")
            return redirect(url_for("login"))

        session.clear()
        session["user"] = {
            "id": perfil["id"],
            "email": perfil["email"]
        }

        flash("Bem-vindo ao VOX! 💜")
        return redirect(url_for("feed"))

    return render_template_string("""
    <h1>Entrar no VOX 🎙️</h1>
    <form method="POST">
      <input name="email" type="email" placeholder="E-mail" required>
      <input name="senha" type="password" placeholder="Senha" required>
      <button type="submit">Entrar</button>
    </form>
    <a href="/cadastro">Criar conta</a>
    """)


@app.route("/logout")
@login_required
def logout():
    session.clear()
    flash("Você saiu da sua conta.")
    return redirect(url_for("login"))
    
def get_media_url(path):
    if not path:
        return None

    try:
        result = sb.storage.from_(BUCKET).create_signed_url(
            path, 3600
        )
        return result.get("signedURL") or result.get("signedUrl")
    except Exception:
        return None


def get_feed_posts(limit=50):
    result = (
        sb.table("posts")
        .select("*")
        .order("created_at", desc=True)
        .limit(limit)
        .execute()
    )

    posts = result.data or []

    for post in posts:
        post["media_url"] = get_media_url(
            post.get("file_path")
        )

        post["author"] = get_profile(
            post.get("user_id")
        )

        post["likes_count"] = (
            sb.table("likes")
            .select("id", count="exact")
            .eq("post_id", post["id"])
            .execute()
            .count or 0
        )

        post["liked"] = False

        if current_user_id():
            liked = (
                sb.table("likes")
                .select("id")
                .eq("post_id", post["id"])
                .eq("user_id", current_user_id())
                .limit(1)
                .execute()
            )
            post["liked"] = bool(liked.data)

    return posts


@app.route("/")
@app.route("/feed")
def feed():
    posts = get_feed_posts()

    return render_template_string("""
    <!doctype html>
    <html lang="pt-br">
    <head>
      <meta charset="utf-8">
      <meta name="viewport" content="width=device-width, initial-scale=1">
      <title>VOX — Sua voz, sua rede</title>
      <style>
        body {
          background: #160d25;
          color: white;
          font-family: Arial, sans-serif;
          margin: 0;
          padding: 18px;
        }
        header {
          display: flex;
          justify-content: space-between;
          align-items: center;
          gap: 10px;
          flex-wrap: wrap;
        }
        h1 { color: #c9a3ff; }
        a { color: #d9bdff; }
        .post {
          background: #28183a;
          border-radius: 14px;
          padding: 16px;
          margin: 18px 0;
        }
        .post img {
          max-width: 100%;
          border-radius: 10px;
        }
        audio { width: 100%; margin-top: 12px; }
        button {
          background: #8b4bd8;
          color: white;
          border: 0;
          border-radius: 8px;
          padding: 10px 14px;
        }
      </style>
    </head>
    <body>
      <header>
        <h1>VOX 🎙️</h1>
        <strong>Sua voz, sua rede. 💜</strong>
      </header>

      <nav>
        {% if session.get("user") %}
          <a href="/perfil/{{ session['user']['id'] }}">Meu perfil</a> |
          <a href="/publicar">Publicar</a> |
          <a href="/logout">Sair</a>
        {% else %}
          <a href="/login">Entrar</a> |
          <a href="/cadastro">Criar conta</a>
        {% endif %}
      </nav>

      <h2>Feed</h2>

      {% for post in posts %}
        <article class="post">
          {% if post.author %}
            <strong>{{ post.author.get("name", "Usuário") }}</strong>
            <span>@{{ post.author.get("username", "") }}</span>
          {% endif %}

          <p>{{ post.get("caption", "") }}</p>

          {% if post.get("media_url") %}
            {% if post.get("type") == "photo" %}
              <img src="{{ post.media_url }}" alt="Foto publicada">
            {% elif post.get("type") == "audio" %}
              <audio controls preload="none">
                <source src="{{ post.media_url }}">
              </audio>
            {% endif %}
          {% endif %}

          <p>❤️ {{ post.likes_count }} curtidas</p>

          {% if session.get("user") %}
            <form method="POST"
                  action="/curtir/{{ post.id }}">
              <button type="submit">
                {% if post.liked %}Descurtir{% else %}Curtir{% endif %}
              </button>
            </form>
          {% endif %}
        </article>
      {% else %}
        <p>Ainda não há publicações. Seja o primeiro a publicar! 💜</p>
      {% endfor %}
    </body>
    </html>
    """, posts=posts)


@app.route("/publicacao/<post_id>")
def visualizar_publicacao(post_id):
    post = get_post(post_id)

    if not post:
        abort(404)

    post["media_url"] = get_media_url(
        post.get("file_path")
    )
    post["author"] = get_profile(
        post.get("user_id")
    )

    return render_template_string("""
    <h1>Publicação VOX 💜</h1>

    {% if post.author %}
      <h3>{{ post.author.get("name", "Usuário") }}</h3>
      <p>@{{ post.author.get("username", "") }}</p>
    {% endif %}

    <p>{{ post.get("caption", "") }}</p>

    {% if post.media_url and post.get("type") == "audio" %}
      <audio controls>
        <source src="{{ post.media_url }}">
      </audio>
    {% elif post.media_url and post.get("type") == "photo" %}
      <img src="{{ post.media_url }}" style="max-width:100%">
    {% endif %}

    <p><a href="/">Voltar ao feed</a></p>
    """, post=post)

def upload_media(file, allowed_extensions):
    if not file or not file.filename:
        raise ValueError("Selecione um arquivo.")

    if not allowed_file(file.filename, allowed_extensions):
        raise ValueError("Formato de arquivo não permitido.")

    file_data = file.read()

    if not file_data:
        raise ValueError("O arquivo está vazio.")

    if len(file_data) > MAX_FILE_SIZE:
        raise ValueError("O arquivo ultrapassa o limite de 50 MB.")

    filename = secure_filename(file.filename)

    if "." not in filename:
        raise ValueError("Nome de arquivo inválido.")

    extension = filename.rsplit(".", 1)[1].lower()
    path = new_storage_path(filename)

    content_types = {
        "mp3": "audio/mpeg",
        "wav": "audio/wav",
        "m4a": "audio/mp4",
        "ogg": "audio/ogg",
        "opus": "audio/ogg",
        "aac": "audio/aac",
        "flac": "audio/flac",
        "webm": "audio/webm",
        "mp4": "video/mp4",
        "jpg": "image/jpeg",
        "jpeg": "image/jpeg",
        "png": "image/png",
        "webp": "image/webp"
    }

    sb.storage.from_(BUCKET).upload(
        path,
        file_data,
        {
            "content-type": content_types.get(
                extension, "application/octet-stream"
            ),
            "upsert": "false"
        }
    )

    return path


@app.route("/publicar", methods=["GET", "POST"])
@login_required
def publicar():
    if request.method == "POST":
        tipo = request.form.get("type", "").strip()
        legenda = request.form.get("caption", "").strip()

        if len(legenda) > 2000:
            flash("A legenda ultrapassou o limite.")
            return redirect(url_for("publicar"))

        if tipo == "audio":
            file = request.files.get("media")
            extensions = AUDIO_EXT
        elif tipo == "photo":
            file = request.files.get("media")
            extensions = IMAGE_EXT
        else:
            flash("Escolha áudio ou foto.")
            return redirect(url_for("publicar"))

        try:
            path = upload_media(file, extensions)

            resultado = sb.table("posts").insert({
                "user_id": current_user_id(),
                "type": tipo,
                "caption": legenda,
                "file_path": path,
                "created_at": utcnow()
            }).execute()

            if not resultado.data:
                sb.storage.from_(BUCKET).remove([path])
                flash("Não foi possível publicar.")
                return redirect(url_for("publicar"))

            flash("Publicação enviada com sucesso! 💜")
            return redirect(url_for("feed"))

        except ValueError as error:
            flash(str(error))
        except Exception:
            flash("Erro ao enviar a publicação. Tente novamente.")

        return redirect(url_for("publicar"))

    return render_template_string("""
    <h1>Nova publicação 🎙️</h1>

    <form method="POST" enctype="multipart/form-data">
      <label>Tipo de publicação</label>
      <select name="type" required>
        <option value="audio">Áudio</option>
        <option value="photo">Foto</option>
      </select>

      <p>Selecione seu arquivo:</p>
      <input type="file" name="media" required>

      <p>Legenda:</p>
      <textarea name="caption"
                maxlength="2000"
                placeholder="Escreva algo..."></textarea>

      <button type="submit">Publicar</button>
    </form>

    <p><a href="/">Voltar ao feed</a></p>
    """)


@app.errorhandler(413)
def arquivo_muito_grande(error):
    return "Arquivo muito grande.", 413
            
@app.route("/curtir/<post_id>", methods=["POST"])
@login_required
def curtir(post_id):
    post = get_post(post_id)

    if not post:
        abort(404)

    user_id = current_user_id()

    existente = (
        sb.table("likes")
        .select("id")
        .eq("post_id", post_id)
        .eq("user_id", user_id)
        .limit(1)
        .execute()
    )

    if existente.data:
        (
            sb.table("likes")
            .delete()
            .eq("post_id", post_id)
            .eq("user_id", user_id)
            .execute()
        )
    else:
        sb.table("likes").insert({
            "post_id": post_id,
            "user_id": user_id,
            "created_at": utcnow()
        }).execute()

    return redirect(
        request.referrer or url_for("feed")
    )


@app.route("/comentario-audio/<post_id>", methods=["POST"])
@login_required
def comentario_audio(post_id):
    post = get_post(post_id)

    if not post:
        abort(404)

    if post.get("type") != "photo":
        flash("Comentários em áudio estão disponíveis nas fotos.")
        return redirect(url_for("visualizar_publicacao",
                                post_id=post_id))

    file = request.files.get("media")

    try:
        path = upload_media(file, AUDIO_EXT)

        resultado = sb.table("comments").insert({
            "post_id": post_id,
            "user_id": current_user_id(),
            "file_path": path,
            "type": "audio",
            "created_at": utcnow()
        }).execute()

        if not resultado.data:
            sb.storage.from_(BUCKET).remove([path])
            flash("Não foi possível enviar o comentário.")
        else:
            flash("Comentário em áudio publicado! 💜")

    except ValueError as error:
        flash(str(error))
    except Exception:
        flash("Erro ao enviar o comentário.")

    return redirect(
        url_for("visualizar_publicacao", post_id=post_id)
    )


def get_audio_comments(post_id):
    result = (
        sb.table("comments")
        .select("*")
        .eq("post_id", post_id)
        .order("created_at", desc=False)
        .execute()
    )

    comments = result.data or []

    for comment in comments:
        comment["media_url"] = get_media_url(
            comment.get("file_path")
        )
        comment["author"] = get_profile(
            comment.get("user_id")
        )

    return comments
        
@app.route(
    "/responder-audio/<comment_id>",
    methods=["POST"]
)
@login_required
def responder_audio(comment_id):
    # Localiza o comentário original
    resultado = (
        sb.table("comments")
        .select("*")
        .eq("id", comment_id)
        .maybe_single()
        .execute()
    )

    comment = resultado.data

    if not comment:
        abort(404)

    # Confirma que o comentário pertence a uma foto
    post = get_post(comment.get("post_id"))

    if not post or post.get("type") != "photo":
        abort(400)

    file = request.files.get("media")

    try:
        path = upload_media(file, AUDIO_EXT)

        resposta = sb.table("replies").insert({
            "comment_id": comment_id,
            "post_id": comment["post_id"],
            "user_id": current_user_id(),
            "file_path": path,
            "type": "audio",
            "created_at": utcnow()
        }).execute()

        if not resposta.data:
            sb.storage.from_(BUCKET).remove([path])
            flash("Não foi possível enviar a resposta.")
        else:
            flash("Resposta em áudio enviada! 💜")

    except ValueError as error:
        flash(str(error))
    except Exception:
        flash("Erro ao enviar a resposta.")

    return redirect(
        url_for(
            "visualizar_publicacao",
            post_id=comment["post_id"]
        )
    )


def get_comment_replies(comment_id):
    resultado = (
        sb.table("replies")
        .select("*")
        .eq("comment_id", comment_id)
        .order("created_at", desc=False)
        .execute()
    )

    replies = resultado.data or []

    for reply in replies:
        reply["media_url"] = get_media_url(
            reply.get("file_path")
        )
        reply["author"] = get_profile(
            reply.get("user_id")
        )

    return replies

@app.route("/perfil/<user_id>")
def perfil(user_id):
    profile_data = get_profile(user_id)

    if not profile_data:
        abort(404)

    posts = (
        sb.table("posts")
        .select("*")
        .eq("user_id", user_id)
        .order("created_at", desc=True)
        .execute()
    ).data or []

    for post in posts:
        post["media_url"] = get_media_url(
            post.get("file_path")
        )

    seguidores = (
        sb.table("follows")
        .select("id", count="exact")
        .eq("following_id", user_id)
        .execute()
    ).count or 0

    seguindo = (
        sb.table("follows")
        .select("id", count="exact")
        .eq("follower_id", user_id)
        .execute()
    ).count or 0

    ja_segue = False

    if current_user_id() and current_user_id() != user_id:
        check = (
            sb.table("follows")
            .select("id")
            .eq("follower_id", current_user_id())
            .eq("following_id", user_id)
            .limit(1)
            .execute()
        )
        ja_segue = bool(check.data)

    return render_template_string("""
    <h1>{{ profile.name }}</h1>
    <h3>@{{ profile.username }}</h3>

    {% if profile.avatar_url %}
      <img src="{{ profile.avatar_url }}"
           style="width:120px;height:120px;border-radius:50%">
    {% endif %}

    <p>{{ profile.get("bio", "") }}</p>

    <p>
      <a href="/seguidores/{{ profile.id }}">
        {{ seguidores }} seguidores
      </a>
      |
      <a href="/seguindo/{{ profile.id }}">
        {{ seguindo }} seguindo
      </a>
    </p>

    {% if session.get("user") %}
      {% if session["user"]["id"] == profile.id %}
        <a href="/editar-perfil">Editar perfil</a>
      {% elif ja_segue %}
        <form method="POST" action="/deixar-de-seguir/{{ profile.id }}">
          <button>Deixar de seguir</button>
        </form>
      {% else %}
        <form method="POST" action="/seguir/{{ profile.id }}">
          <button>Seguir</button>
        </form>
      {% endif %}
    {% endif %}

    <h2>Publicações</h2>

    {% for post in posts %}
      <article>
        <p>{{ post.get("caption", "") }}</p>

        {% if post.media_url and post.type == "audio" %}
          <audio controls>
            <source src="{{ post.media_url }}">
          </audio>
        {% elif post.media_url and post.type == "photo" %}
          <img src="{{ post.media_url }}" style="max-width:100%">
        {% endif %}
      </article>
    {% else %}
      <p>Nenhuma publicação ainda.</p>
    {% endfor %}

    <a href="/">Voltar ao feed</a>
    """, profile=profile_data, posts=posts,
       seguidores=seguidores, seguindo=seguindo,
       ja_segue=ja_segue)


@app.route("/editar-perfil", methods=["GET", "POST"])
@login_required
def editar_perfil():
    user_id = current_user_id()
    profile_data = get_profile(user_id)

    if not profile_data:
        abort(404)

    if request.method == "POST":
        nome = request.form.get("nome", "").strip()
        bio = request.form.get("bio", "").strip()
        username = request.form.get("username", "").strip().lower()

        if not nome or len(nome) > 60:
            flash("Informe um nome válido.")
            return redirect(url_for("editar_perfil"))

        if len(bio) > 300:
            flash("A biografia pode ter até 300 caracteres.")
            return redirect(url_for("editar_perfil"))

        if not valid_username(username):
            flash("Nome de usuário inválido.")
            return redirect(url_for("editar_perfil"))

        existente = (
            sb.table("profiles")
            .select("id")
            .eq("username", username)
            .neq("id", user_id)
            .limit(1)
            .execute()
        )

        if existente.data:
            flash("Esse @ já está sendo utilizado.")
            return redirect(url_for("editar_perfil"))

        dados = {
            "name": nome,
            "username": username,
            "bio": bio
        }

        avatar = request.files.get("avatar")

        if avatar and avatar.filename:
            try:
                avatar_path = upload_media(avatar, IMAGE_EXT)
                dados["avatar_path"] = avatar_path
                dados["avatar_url"] = get_media_url(avatar_path)
            except ValueError as error:
                flash(str(error))
                return redirect(url_for("editar_perfil"))

        sb.table("profiles").update(dados).eq(
            "id", user_id
        ).execute()

        flash("Perfil atualizado! 💜")
        return redirect(url_for("perfil", user_id=user_id))

    return render_template_string("""
    <h1>Editar perfil 💜</h1>

    <form method="POST" enctype="multipart/form-data">
      <p>Nome:</p>
      <input name="nome"
             value="{{ profile.name }}"
             maxlength="60" required>

      <p>Nome de usuário:</p>
      <input name="username"
             value="{{ profile.username }}"
             required>

      <p>Biografia:</p>
      <textarea name="bio"
                maxlength="300">{{ profile.get("bio", "") }}</textarea>

      <p>Foto de perfil:</p>
      <input type="file" name="avatar"
             accept=".jpg,.jpeg,.png,.webp">

      <button type="submit">Salvar alterações</button>
    </form>
    """, profile=profile_data)
        
@app.route("/seguir/<user_id>", methods=["POST"])
@login_required
def seguir(user_id):
    meu_id = current_user_id()

    if meu_id == user_id:
        flash("Você não pode seguir a si mesmo.")
        return redirect(url_for("perfil", user_id=user_id))

    if not get_profile(user_id):
        abort(404)

    existente = (
        sb.table("follows")
        .select("id")
        .eq("follower_id", meu_id)
        .eq("following_id", user_id)
        .limit(1)
        .execute()
    )

    if not existente.data:
        sb.table("follows").insert({
            "follower_id": meu_id,
            "following_id": user_id,
            "created_at": utcnow()
        }).execute()

    return redirect(url_for("perfil", user_id=user_id))


@app.route("/deixar-de-seguir/<user_id>", methods=["POST"])
@login_required
def deixar_de_seguir(user_id):
    meu_id = current_user_id()

    sb.table("follows").delete().eq(
        "follower_id", meu_id
    ).eq(
        "following_id", user_id
    ).execute()

    return redirect(url_for("perfil", user_id=user_id))


@app.route("/seguidores/<user_id>")
def lista_seguidores(user_id):
    profile_data = get_profile(user_id)

    if not profile_data:
        abort(404)

    resultado = (
        sb.table("follows")
        .select("follower_id")
        .eq("following_id", user_id)
        .execute()
    )

    pessoas = []

    for item in resultado.data or []:
        pessoa = get_profile(item["follower_id"])

        if pessoa:
            pessoas.append(pessoa)

    return render_template_string("""
    <h1>Seguidores de @{{ profile.username }}</h1>

    {% for pessoa in pessoas %}
      <p>
        <a href="/perfil/{{ pessoa.id }}">
          {{ pessoa.name }} — @{{ pessoa.username }}
        </a>
      </p>
    {% else %}
      <p>Ninguém segue esta conta ainda.</p>
    {% endfor %}

    <a href="/perfil/{{ profile.id }}">Voltar ao perfil</a>
    """, profile=profile_data, pessoas=pessoas)


@app.route("/seguindo/<user_id>")
def lista_seguindo(user_id):
    profile_data = get_profile(user_id)

    if not profile_data:
        abort(404)

    resultado = (
        sb.table("follows")
        .select("following_id")
        .eq("follower_id", user_id)
        .execute()
    )

    pessoas = []

    for item in resultado.data or []:
        pessoa = get_profile(item["following_id"])

        if pessoa:
            pessoas.append(pessoa)

    return render_template_string("""
    <h1>Quem @{{ profile.username }} segue</h1>

    {% for pessoa in pessoas %}
      <p>
        <a href="/perfil/{{ pessoa.id }}">
          {{ pessoa.name }} — @{{ pessoa.username }}
        </a>
      </p>
    {% else %}
      <p>Esta conta ainda não segue ninguém.</p>
    {% endfor %}

    <a href="/perfil/{{ profile.id }}">Voltar ao perfil</a>
    """, profile=profile_data, pessoas=pessoas)
    
@app.route("/denunciar/<post_id>", methods=["POST"])
@login_required
def denunciar_publicacao(post_id):
    post = get_post(post_id)

    if not post:
        abort(404)

    motivo = request.form.get("motivo", "").strip()
    detalhes = request.form.get("detalhes", "").strip()

    motivos_validos = {
        "spam",
        "conteudo_inadequado",
        "assedio",
        "violacao_de_direitos",
        "outro"
    }

    if motivo not in motivos_validos:
        flash("Selecione um motivo válido.")
        return redirect(
            url_for("visualizar_publicacao", post_id=post_id)
        )

    if len(detalhes) > 1000:
        flash("Os detalhes ultrapassaram o limite.")
        return redirect(
            url_for("visualizar_publicacao", post_id=post_id)
        )

    sb.table("reports").insert({
        "post_id": post_id,
        "reporter_id": current_user_id(),
        "reason": motivo,
        "details": detalhes,
        "status": "pending",
        "created_at": utcnow()
    }).execute()

    flash("Denúncia enviada para análise. Obrigado!")
    return redirect(
        url_for("visualizar_publicacao", post_id=post_id)
    )


@app.route("/admin/denuncias")
@admin_required
def admin_denuncias():
    resultado = (
        sb.table("reports")
        .select("*")
        .order("created_at", desc=True)
        .execute()
    )

    denuncias = resultado.data or []

    for denuncia in denuncias:
        denuncia["post"] = get_post(
            denuncia.get("post_id")
        )
        denuncia["reporter"] = get_profile(
            denuncia.get("reporter_id")
        )

    return render_template_string("""
    <h1>Denúncias — VOX 🛡️</h1>

    {% for denuncia in denuncias %}
      <article style="padding:15px;margin:12px 0;
                      background:#28183a;color:white">
        <h3>Denúncia #{{ denuncia.id }}</h3>

        <p>Motivo: {{ denuncia.reason }}</p>
        <p>Detalhes: {{ denuncia.details or "Sem detalhes" }}</p>
        <p>Status: {{ denuncia.status }}</p>

        {% if denuncia.reporter %}
          <p>
            Denunciado por:
            @{{ denuncia.reporter.username }}
          </p>
        {% endif %}

        {% if denuncia.post %}
          <a href="/publicacao/{{ denuncia.post.id }}">
            Ver publicação
          </a>
        {% else %}
          <p>Publicação não encontrada.</p>
        {% endif %}

        <form method="POST"
              action="/admin/denuncia/{{ denuncia.id }}/analisar">
          <button type="submit">Marcar como analisada</button>
        </form>
      </article>
    {% else %}
      <p>Nenhuma denúncia registrada.</p>
    {% endfor %}

    <a href="/admin">Voltar ao painel</a>
    """, denuncias=denuncias)


@app.route(
    "/admin/denuncia/<report_id>/analisar",
    methods=["POST"]
)
@admin_required
def analisar_denuncia(report_id):
    resultado = (
        sb.table("reports")
        .update({
            "status": "reviewed"
        })
        .eq("id", report_id)
        .execute()
    )

    if not resultado.data:
        abort(404)

    flash("Denúncia marcada como analisada.")
    return redirect(url_for("admin_denuncias"))
   
@app.route("/admin")
@admin_required
def painel_admin():
    total_posts = (
        sb.table("posts")
        .select("id", count="exact")
        .execute()
        .count or 0
    )

    total_users = (
        sb.table("profiles")
        .select("id", count="exact")
        .execute()
        .count or 0
    )

    total_reports = (
        sb.table("reports")
        .select("id", count="exact")
        .eq("status", "pending")
        .execute()
        .count or 0
    )

    return render_template_string("""
    <h1>VOX — Administração 🛡️</h1>

    <h2>Visão geral</h2>
    <p>Usuários: {{ users }}</p>
    <p>Publicações: {{ posts }}</p>
    <p>Denúncias pendentes: {{ reports }}</p>

    <nav>
      <p><a href="/admin/denuncias">🚩 Denúncias</a></p>
      <p><a href="/admin/publicacoes">🎙️ Publicações</a></p>
      <p><a href="/admin/lixeira">🗑️ Lixeira</a></p>
      <p><a href="/">Voltar ao VOX</a></p>
    </nav>
    """, users=total_users, posts=total_posts,
       reports=total_reports)


@app.route("/admin/publicacoes")
@admin_required
def admin_publicacoes():
    resultado = (
        sb.table("posts")
        .select("*")
        .order("created_at", desc=True)
        .execute()
    )

    posts = resultado.data or []

    for post in posts:
        post["author"] = get_profile(post.get("user_id"))

    return render_template_string("""
    <h1>Publicações — Administração</h1>

    {% for post in posts %}
      <article style="padding:15px;margin:12px 0;
                      background:#28183a;color:white">
        <p>ID: {{ post.id }}</p>
        <p>Tipo: {{ post.type }}</p>
        <p>{{ post.caption or "" }}</p>

        {% if post.author %}
          <p>Autor: @{{ post.author.username }}</p>
        {% endif %}

        <a href="/publicacao/{{ post.id }}">Visualizar</a>

        <form method="POST"
              action="/admin/enviar-lixeira/{{ post.id }}">
          <button type="submit">Mover para lixeira</button>
        </form>
      </article>
    {% else %}
      <p>Nenhuma publicação encontrada.</p>
    {% endfor %}

    <a href="/admin">Voltar ao painel</a>
    """, posts=posts)


@app.route(
    "/admin/enviar-lixeira/<post_id>",
    methods=["POST"]
)
@admin_required
def enviar_lixeira(post_id):
    post = get_post(post_id)

    if not post:
        abort(404)

    resultado = (
        sb.table("posts")
        .update({
            "deleted_at": utcnow(),
            "deleted_by": current_user_id()
        })
        .eq("id", post_id)
        .execute()
    )

    if not resultado.data:
        abort(404)

    flash("Publicação movida para a lixeira.")
    return redirect(url_for("admin_publicacoes"))


@app.route("/admin/lixeira")
@admin_required
def admin_lixeira():
    resultado = (
        sb.table("posts")
        .select("*")
        .not_.is_("deleted_at", "null")
        .order("deleted_at", desc=True)
        .execute()
    )

    posts = resultado.data or []

    return render_template_string("""
    <h1>Lixeira do VOX 🗑️</h1>

    {% for post in posts %}
      <article>
        <p>Publicação: {{ post.id }}</p>
        <p>{{ post.caption or "" }}</p>

        <form method="POST"
              action="/admin/restaurar/{{ post.id }}">
          <button>Restaurar</button>
        </form>

        <form method="POST"
              action="/admin/excluir-permanente/{{ post.id }}">
          <button>Excluir permanentemente</button>
        </form>
      </article>
    {% else %}
      <p>A lixeira está vazia.</p>
    {% endfor %}

    <a href="/admin">Voltar ao painel</a>
    """, posts=posts)


@app.route(
    "/admin/restaurar/<post_id>",
    methods=["POST"]
)
@admin_required
def restaurar_publicacao(post_id):
    resultado = (
        sb.table("posts")
        .update({
            "deleted_at": None,
            "deleted_by": None
        })
        .eq("id", post_id)
        .execute()
    )

    if not resultado.data:
        abort(404)

    flash("Publicação restaurada.")
    return redirect(url_for("admin_lixeira"))
    
def remove_storage_files(paths):
    valid_paths = list({
        path for path in paths
        if isinstance(path, str) and path.strip()
    })

    if valid_paths:
        sb.storage.from_(BUCKET).remove(valid_paths)


def collect_post_storage_paths(post_id):
    paths = []

    post = get_post(post_id)

    if post and post.get("file_path"):
        paths.append(post["file_path"])

    comments = (
        sb.table("comments")
        .select("file_path")
        .eq("post_id", post_id)
        .execute()
    ).data or []

    for comment in comments:
        if comment.get("file_path"):
            paths.append(comment["file_path"])

    replies = (
        sb.table("replies")
        .select("file_path")
        .eq("post_id", post_id)
        .execute()
    ).data or []

    for reply in replies:
        if reply.get("file_path"):
            paths.append(reply["file_path"])

    return paths


@app.route(
    "/admin/excluir-permanente/<post_id>",
    methods=["POST"]
)
@admin_required
def excluir_permanentemente(post_id):
    post = get_post(post_id)

    if not post:
        abort(404)

    if not post.get("deleted_at"):
        flash("Mova a publicação para a lixeira primeiro.")
        return redirect(url_for("admin_lixeira"))

    try:
        paths = collect_post_storage_paths(post_id)

        # Remove a publicação do banco.
        # As tabelas relacionadas precisam ter ON DELETE CASCADE.
        resultado = (
            sb.table("posts")
            .delete()
            .eq("id", post_id)
            .execute()
        )

        if not resultado.data:
            flash("Não foi possível excluir a publicação.")
            return redirect(url_for("admin_lixeira"))

        # Remove os arquivos do armazenamento.
        remove_storage_files(paths)

        flash("Publicação excluída permanentemente.")

    except Exception:
        flash("Erro durante a exclusão. Verifique o banco e o armazenamento.")

    return redirect(url_for("admin_lixeira"))


@app.route("/admin/usuario/<user_id>")
@admin_required
def admin_visualizar_usuario(user_id):
    profile_data = get_profile(user_id)

    if not profile_data:
        abort(404)

    return render_template_string("""
    <h1>Usuário — Administração</h1>

    <p>Nome: {{ profile.name }}</p>
    <p>@{{ profile.username }}</p>
    <p>E-mail: {{ profile.email }}</p>
    <p>Biografia: {{ profile.get("bio", "") }}</p>

    <a href="/perfil/{{ profile.id }}">Abrir perfil</a>
    <p><a href="/admin">Voltar ao painel</a></p>
    """, profile=profile_data)
    
@app.route("/saude")
def saude():
    return jsonify({
        "app": "VOX",
        "version": "3.0",
        "status": "online"
    })


@app.errorhandler(403)
def acesso_negado(error):
    return render_template_string("""
    <h1>403 — Acesso negado</h1>
    <p>Você não tem permissão para acessar esta página.</p>
    <a href="/">Voltar ao VOX 💜</a>
    """), 403


@app.errorhandler(404)
def pagina_nao_encontrada(error):
    return render_template_string("""
    <h1>404 — Página não encontrada</h1>
    <p>Não encontramos o que você procura.</p>
    <a href="/">Voltar ao VOX 💜</a>
    """), 404


@app.errorhandler(500)
def erro_interno(error):
    return render_template_string("""
    <h1>500 — Erro interno</h1>
    <p>Ocorreu um problema. Tente novamente mais tarde.</p>
    <a href="/">Voltar ao VOX 💜</a>
    """), 500


@app.route("/robots.txt")
def robots():
    return "User-agent: *\nDisallow: /admin\n", 200, {
        "Content-Type": "text/plain"
    }


if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 5000)),
        debug=False
    )
    
