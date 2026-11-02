import os, re, uuid, mimetypes
from functools import wraps
from datetime import datetime, timezone
from flask import Flask, request, redirect, url_for, session, flash, render_template_string, abort
from supabase import create_client

# VOX - reconstrução do app.py com Supabase
# Render: SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY, SECRET_KEY, ADMIN_EMAIL
app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'troque-esta-chave-no-render')
app.config['MAX_CONTENT_LENGTH'] = 60 * 1024 * 1024
URL = os.environ.get('SUPABASE_URL', '').strip()
KEY = os.environ.get('SUPABASE_SERVICE_ROLE_KEY', '').strip()
ADMIN_EMAIL = os.environ.get('ADMIN_EMAIL', '').strip().lower()
if not URL or not KEY:
    raise RuntimeError('Configure SUPABASE_URL e SUPABASE_SERVICE_ROLE_KEY no Render.')
sb = create_client(URL, KEY)
BUCKET = 'vox-audios'
AUDIO = {'mp3','wav','m4a','ogg','opus','aac','flac','webm','mp4'}
IMAGE = {'jpg','jpeg','png','webp'}

# Helpers
def ext(name): return name.rsplit('.',1)[-1].lower() if '.' in name else ''
def user():
    uid=session.get('user_id')
    if not uid: return None
    try: return sb.table('profiles').select('*').eq('id',uid).maybe_single().execute().data
    except Exception: return None
def login_required(fn):
    @wraps(fn)
    def w(*a,**k):
        if not user(): session.clear(); flash('Entre na sua conta.'); return redirect(url_for('login'))
        return fn(*a,**k)
    return w
def admin_required(fn):
    @wraps(fn)
    def w(*a,**k):
        u=user()
        if not u or not u.get('is_admin'): abort(403)
        return fn(*a,**k)
    return w
def upload(f, allowed, folder):
    if not f or not f.filename or ext(f.filename) not in allowed: raise ValueError('Formato de arquivo não permitido.')
    data=f.read()
    if not data: raise ValueError('Arquivo vazio.')
    if len(data)>50*1024*1024: raise ValueError('O arquivo ultrapassa 50 MB.')
    path=f'{folder}/{uuid.uuid4().hex}.{ext(f.filename)}'
    sb.storage.from_(BUCKET).upload(path,data,{'content-type':f.mimetype or mimetypes.guess_type(f.filename)[0] or 'application/octet-stream','upsert':'false'})
    return path
def media(path):
    if not path: return ''
    try:
        x=sb.storage.from_(BUCKET).create_signed_url(path,3600)
        d=x if isinstance(x,dict) else getattr(x,'data',{})
        return d.get('signedURL') or d.get('signedUrl') or d.get('signed_url') or ''
    except Exception: return ''
def profile(uid):
    try: return sb.table('profiles').select('*').eq('id',uid).maybe_single().execute().data
    except Exception: return None
def page(title, body, **ctx):
    html='''<!doctype html><html lang="pt-br"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{{ title }} · VOX</title><style>
:root{color-scheme:dark}*{box-sizing:border-box}body{margin:0;background:#100b1c;color:white;font:16px Arial}header{background:#1a1029;padding:15px 5%;display:flex;justify-content:space-between;gap:15px;flex-wrap:wrap;border-bottom:1px solid #493263}a{color:#d8b4fe;text-decoration:none}.brand{font-size:25px;font-weight:bold;color:white}nav{display:flex;gap:13px;flex-wrap:wrap}main{max-width:850px;margin:25px auto;padding:0 15px}.card{background:#1c1430;border:1px solid #493263;border-radius:15px;padding:18px;margin:15px 0}input,textarea,select{width:100%;padding:11px;margin:6px 0 12px;border-radius:9px;background:#100b1c;color:white;border:1px solid #574071}button,.btn{background:#8b5cf6;color:white;border:0;border-radius:9px;padding:10px 15px;cursor:pointer;display:inline-block}audio{width:100%;margin:10px 0}.photo{max-width:100%;max-height:550px;display:block;margin:12px auto;border-radius:12px}.muted,small{color:#b9abc9}.notice{background:#302044;padding:10px;border-radius:9px;margin:10px 0}.inline{display:inline}.danger{background:#a8325c}
</style></head><body><header><div><a class="brand" href="{{ url_for('feed') }}">VOX</a><div style="color:#c4b5fd">Sua voz, sua rede. 💜</div></div><nav><a href="{{ url_for('feed') }}">Início</a>{% if current %}<a href="{{ url_for('publish') }}">Publicar</a><a href="{{ url_for('profile_page',username=current.username) }}">Meu perfil</a>{% if current.is_admin %}<a href="{{ url_for('admin') }}">Admin</a>{% endif %}<a href="{{ url_for('logout') }}">Sair</a>{% else %}<a href="{{ url_for('login') }}">Entrar</a><a href="{{ url_for('register') }}">Criar conta</a>{% endif %}</nav></header><main>{% with ms=get_flashed_messages() %}{% for m in ms %}<div class="notice">{{ m }}</div>{% endfor %}{% endwith %}'''+body+'</main></body></html>'
    return render_template_string(html,title=title,current=user(),**ctx)

# Feed
@app.route('/')
def feed():
    posts=sb.table('posts').select('*').is_('deleted_at','null').order('created_at',desc=True).limit(100).execute().data or []
    for p in posts:
        p['author']=profile(p['user_id']) or {'username':'conta','display_name':'Conta'}
        p['url']=media(p.get('media_path'))
        p['likes']=len(sb.table('likes').select('id').eq('post_id',p['id']).execute().data or [])
    return page('Início','''<h2>Feed VOX 💜</h2>{% for p in posts %}<article class="card"><b><a href="{{ url_for('profile_page',username=p.author.username) }}">{{ p.author.display_name or p.author.username }} · @{{ p.author.username }}</a></b><p>{{ p.caption or '' }}</p>{% if p.kind=='audio' %}<audio controls preload="none" src="{{ p.url }}"></audio>{% else %}<img class="photo" src="{{ p.url }}">{% endif %}<form class="inline" method="post" action="{{ url_for('like',post_id=p.id) }}"><button>💜 Curtir · {{ p.likes }}</button></form> <a href="{{ url_for('post',post_id=p.id) }}">Comentários</a><form class="inline" method="post" action="{{ url_for('report',post_id=p.id) }}"><button class="danger">Denunciar</button></form></article>{% else %}<div class="card">Ainda não há publicações.</div>{% endfor %}''',posts=posts)

# Account
@app.route('/cadastro',methods=['GET','POST'])
def register():
    if request.method=='POST':
        email=request.form.get('email','').strip().lower(); password=request.form.get('password',''); name=request.form.get('username','').strip().lower().lstrip('@'); display=request.form.get('display_name','').strip() or name
        try:
            if not re.fullmatch(r'[a-z0-9_.]{3,24}',name): raise ValueError('O @ deve ter 3 a 24 caracteres: letras, números, ponto ou underline.')
            if len(password)<8: raise ValueError('A senha precisa ter pelo menos 8 caracteres.')
            if sb.table('profiles').select('id').ilike('username',name).execute().data: raise ValueError('Esse @ já está em uso.')
            auth=sb.auth.sign_up({'email':email,'password':password}); uid=auth.user.id
            sb.table('profiles').insert({'id':uid,'username':name,'display_name':display,'bio':'','is_admin':bool(ADMIN_EMAIL and email==ADMIN_EMAIL)}).execute()
            if auth.session: session['user_id']=uid; return redirect(url_for('feed'))
            flash('Cadastro criado. Confirme o email e depois entre.'); return redirect(url_for('login'))
        except Exception as e: flash(str(e))
    return page('Criar conta','''<div class="card"><h2>Criar conta</h2><form method="post"><label>Nome de exibição</label><input name="display_name"><label>Nome de usuário (@)</label><input name="username" required><label>Email</label><input name="email" type="email" required><label>Senha (mínimo 8 caracteres)</label><input name="password" type="password" required><button>Criar conta</button></form></div>''')
@app.route('/entrar',methods=['GET','POST'])
def login():
    if request.method=='POST':
        try:
            r=sb.auth.sign_in_with_password({'email':request.form.get('email','').strip().lower(),'password':request.form.get('password','')}); session.clear(); session['user_id']=r.user.id; return redirect(url_for('feed'))
        except Exception: flash('Email ou senha inválidos. Confira também a confirmação do email.')
    return page('Entrar','''<div class="card"><h2>Entrar</h2><form method="post"><label>Email</label><input name="email" type="email" required><label>Senha</label><input name="password" type="password" required><button>Entrar</button></form></div>''')
@app.route('/sair')
def logout(): session.clear(); return redirect(url_for('feed'))

# Profiles and follows
@app.route('/u/<username>')
def profile_page(username):
    person=sb.table('profiles').select('*').ilike('username',username).maybe_single().execute().data
    if not person: abort(404)
    posts=sb.table('posts').select('*').eq('user_id',person['id']).is_('deleted_at','null').order('created_at',desc=True).execute().data or []
    for p in posts: p['url']=media(p.get('media_path'))
    followers=len(sb.table('follows').select('id').eq('following_id',person['id']).execute().data or []); following=len(sb.table('follows').select('id').eq('follower_id',person['id']).execute().data or [])
    me=user(); followed=bool(me and sb.table('follows').select('id').eq('follower_id',me['id']).eq('following_id',person['id']).execute().data)
    return page('Perfil','''<div class="card"><h2>{{ person.display_name or person.username }}</h2><b>@{{ person.username }}</b><p>{{ person.bio or '' }}</p><p>
    <a href="{{ url_for('followers_page', username=person.username) }}">
        {{ followers }} seguidores
    </a>
    ·
    <a href="{{ url_for('following_page', username=person.username) }}">
        {{ following }} seguindo
    </a>
    · {{ posts|length }} publicações
</p>{% if current and current.id!=person.id %}<form method="post" action="{{ url_for('follow',uid=person.id) }}"><button>{{ 'Deixar de seguir' if followed else 'Seguir' }}</button></form>{% endif %}{% if current and current.id==person.id %}<a class="btn" href="{{ url_for('edit_profile') }}">Editar perfil</a>{% endif %}</div>{% for p in posts %}<div class="card"><p>{{ p.caption or '' }}</p>{% if p.kind=='audio' %}<audio controls src="{{ p.url }}"></audio>{% else %}<img class="photo" src="{{ p.url }}">{% endif %}<a href="{{ url_for('post',post_id=p.id) }}">Abrir publicação</a></div>{% endfor %}''',person=person,posts=posts,followers=followers,following=following,followed=followed)
@app.route('/perfil/editar',methods=['GET','POST'])
@login_required
def edit_profile():
    me=user()
    if request.method=='POST':
        data={'display_name':request.form.get('display_name','').strip(),'bio':request.form.get('bio','').strip()[:300]}; avatar=request.files.get('avatar')
        if avatar and avatar.filename:
            try: data['avatar_path']=upload(avatar,IMAGE,'avatars')
            except Exception as e: flash(str(e)); return redirect(url_for('edit_profile'))
        sb.table('profiles').update(data).eq('id',me['id']).execute(); flash('Perfil atualizado.'); return redirect(url_for('profile_page',username=me['username']))
    return page('Editar perfil','''<div class="card"><h2>Editar perfil</h2><form method="post" enctype="multipart/form-data"><label>Nome</label><input name="display_name" value="{{ current.display_name or '' }}"><label>Biografia</label><textarea name="bio">{{ current.bio or '' }}</textarea><label>Foto de perfil</label><input type="file" name="avatar" accept=".jpg,.jpeg,.png,.webp"><button>Salvar</button></form></div>''')
@app.route('/seguir/<uid>',methods=['POST'])
@login_required
def follow(uid):
    me=user()
    if uid==me['id']: abort(400)
    q=sb.table('follows').select('id').eq('follower_id',me['id']).eq('following_id',uid).execute().data
    if q: sb.table('follows').delete().eq('follower_id',me['id']).eq('following_id',uid).execute()
    else: sb.table('follows').insert({'follower_id':me['id'],'following_id':uid}).execute()
    return redirect(request.referrer or url_for('feed'))
    # Listas de seguidores e pessoas seguindo

@app.route('/u/<username>/seguidores')
def followers_page(username):
    person = sb.table('profiles').select('*').ilike(
        'username', username
    ).maybe_single().execute().data

    if not person:
        abort(404)

    relations = sb.table('follows').select(
        'follower_id'
    ).eq('following_id', person['id']).execute().data or []

    people = []

    for relation in relations:
        p = profile(relation['follower_id'])
        if p:
            people.append(p)

    return page(
        'Seguidores',
        '''
        <div class="card">
            <h2>Seguidores de @{{ person.username }}</h2>

            {% for p in people %}
                <div class="notice">
                    <a href="{{ url_for(
                        'profile_page',
                        username=p.username
                    ) }}">
                        {{ p.display_name or p.username }}
                        · @{{ p.username }}
                    </a>
                </div>
            {% else %}
                <p class="muted">Nenhum seguidor ainda.</p>
            {% endfor %}
        </div>
        ''',
        person=person,
        people=people
    )


@app.route('/u/<username>/seguindo')
def following_page(username):
    person = sb.table('profiles').select('*').ilike(
        'username', username
    ).maybe_single().execute().data

    if not person:
        abort(404)

    relations = sb.table('follows').select(
        'following_id'
    ).eq('follower_id', person['id']).execute().data or []

    people = []

    for relation in relations:
        p = profile(relation['following_id'])
        if p:
            people.append(p)

    return page(
        'Seguindo',
        '''
        <div class="card">
            <h2>Pessoas que @{{ person.username }} segue</h2>

            {% for p in people %}
                <div class="notice">
                    <a href="{{ url_for(
                        'profile_page',
                        username=p.username
                    ) }}">
                        {{ p.display_name or p.username }}
                        · @{{ p.username }}
                    </a>
                </div>
            {% else %}
                <p class="muted">Ainda não segue ninguém.</p>
            {% endfor %}
        </div>
        ''',
        person=person,
        people=people
    )

# Publish audio/photo
@app.route('/publicar',methods=['GET','POST'])
@login_required
def publish():
    if request.method=='POST':
        kind=request.form.get('kind'); f=request.files.get('media')
        try:
            if kind not in ('audio','photo'): raise ValueError('Tipo de publicação inválido.')
            path=upload(f,AUDIO if kind=='audio' else IMAGE,'posts')
            sb.table('posts').insert({'user_id':user()['id'],'kind':kind,'media_path':path,'caption':request.form.get('caption','').strip()[:500]}).execute(); flash('Publicação enviada!'); return redirect(url_for('feed'))
        except Exception as e: flash(str(e))
    return page('Publicar','''<div class="card"><h2>Nova publicação</h2><form method="post" enctype="multipart/form-data"><label>Tipo</label><select name="kind"><option value="audio">Áudio</option><option value="photo">Foto</option></select><label>Arquivo</label><input type="file" name="media" required><label>Legenda</label><textarea name="caption" maxlength="500"></textarea><button>Publicar</button></form><p class="muted">Limite atual: 50 MB por arquivo.</p></div>''')
@app.route('/curtir/<post_id>',methods=['POST'])
@login_required
def like(post_id):
    uid=user()['id']; q=sb.table('likes').select('id').eq('post_id',post_id).eq('user_id',uid).execute().data
    if q: sb.table('likes').delete().eq('post_id',post_id).eq('user_id',uid).execute()
    else: sb.table('likes').insert({'post_id':post_id,'user_id':uid}).execute()
    return redirect(request.referrer or url_for('feed'))

# Photo comments and audio replies
@app.route('/post/<post_id>')
def post(post_id):
    p=sb.table('posts').select('*').eq('id',post_id).maybe_single().execute().data
    if not p or p.get('deleted_at'): abort(404)
    author=profile(p['user_id']) or {'username':'conta'}; media_url=media(p.get('media_path'))
    comments=sb.table('comments').select('*').eq('post_id',post_id).order('created_at').execute().data or []
    for c in comments:
        c['author']=profile(c['user_id']) or {'username':'conta'}; c['url']=media(c.get('audio'))
        c['replies']=sb.table('replies').select('*').eq('comment_id',c['id']).order('created_at').execute().data or []
        for r in c['replies']: r['author']=profile(r['user_id']) or {'username':'conta'}; r['url']=media(r.get('audio'))
    return page('Publicação','''<div class="card"><a href="{{ url_for('profile_page',username=author.username) }}">@{{ author.username }}</a><p>{{ p.caption or '' }}</p>{% if p.kind=='audio' %}<audio controls src="{{ media_url }}"></audio>{% else %}<img class="photo" src="{{ media_url }}">{% endif %}</div>{% if p.kind=='photo' and current %}<div class="card"><h3>Comentar com áudio</h3><form method="post" enctype="multipart/form-data" action="{{ url_for('comment',post_id=p.id) }}"><input type="file" name="audio" required accept="audio/*"><button>Enviar comentário</button></form></div>{% endif %}{% for c in comments %}<div class="card"><b>@{{ c.author.username }}</b><audio controls src="{{ c.url }}"></audio>{% if current %}<form method="post" enctype="multipart/form-data" action="{{ url_for('reply',comment_id=c.id) }}"><label>Responder com áudio</label><input type="file" name="audio" required accept="audio/*"><button>Responder</button></form>{% endif %}{% for r in c.replies %}<div class="notice">↳ @{{ r.author.username }}<audio controls src="{{ r.url }}"></audio></div>{% endfor %}</div>{% endfor %}''',p=p,author=author,media_url=media_url,comments=comments)
@app.route('/comentar/<post_id>',methods=['POST'])
@login_required
def comment(post_id):
    p=sb.table('posts').select('id,kind').eq('id',post_id).maybe_single().execute().data
    if not p or p['kind']!='photo': abort(404)
    try:
        name=upload(request.files.get('audio'),AUDIO,'comments'); sb.table('comments').insert({'post_id':post_id,'user_id':user()['id'],'audio':name}).execute(); flash('Comentário enviado.')
    except Exception as e: flash(f'Não foi possível comentar: {e}')
    return redirect(url_for('post',post_id=post_id))
@app.route('/responder/<comment_id>',methods=['POST'])
@login_required
def reply(comment_id):
    c=sb.table('comments').select('id,post_id').eq('id',comment_id).maybe_single().execute().data
    if not c: abort(404)
    try:
        name=upload(request.files.get('audio'),AUDIO,'replies'); sb.table('replies').insert({'comment_id':comment_id,'user_id':user()['id'],'audio':name}).execute(); flash('Resposta enviada.')
    except Exception as e: flash(f'Não foi possível responder: {e}')
    return redirect(url_for('post',post_id=c['post_id']))
@app.route('/denunciar/<post_id>',methods=['POST'])
@login_required
def report(post_id):
    try: sb.table('reports').insert({'post_id':post_id,'user_id':user()['id'],'reason':'Denúncia enviada pelo usuário','status':'open'}).execute(); flash('Denúncia enviada para análise.')
    except Exception: flash('Não foi possível denunciar.')
    return redirect(request.referrer or url_for('feed'))

# Admin moderation
@app.route('/admin')
@admin_required
def admin():
    posts=sb.table('posts').select('*').order('created_at',desc=True).limit(200).execute().data or []; reports=sb.table('reports').select('*').order('created_at',desc=True).limit(200).execute().data or []
    for p in posts: p['author']=profile(p['user_id']) or {'username':'conta'}
    return page('Admin','''<div class="card"><h2>Administração VOX</h2></div><h3>Publicações</h3>{% for p in posts %}<div class="card"><b>@{{ p.author.username }}</b> · {{ p.kind }} · {{ p.caption or '' }}{% if p.deleted_at %}<p>Na lixeira</p><form method="post" action="{{ url_for('restore',post_id=p.id) }}"><button>Restaurar</button></form>{% else %}<form method="post" action="{{ url_for('trash',post_id=p.id) }}"><button class="danger">Mover para lixeira</button></form>{% endif %}<form method="post" action="{{ url_for('delete_post',post_id=p.id) }}"><button class="danger">Excluir definitivamente</button></form></div>{% endfor %}<h3>Denúncias</h3>{% for r in reports %}<div class="card">Post {{ r.post_id }} · {{ r.reason or '' }} · {{ r.status or '' }}<form method="post" action="{{ url_for('review_report',rid=r.id) }}"><button>Marcar analisada</button></form></div>{% endfor %}''',posts=posts,reports=reports)
@app.route('/admin/lixeira/<post_id>',methods=['POST'])
@admin_required
def trash(post_id): sb.table('posts').update({'deleted_at':datetime.now(timezone.utc).isoformat()}).eq('id',post_id).execute(); return redirect(url_for('admin'))
@app.route('/admin/restaurar/<post_id>',methods=['POST'])
@admin_required
def restore(post_id): sb.table('posts').update({'deleted_at':None}).eq('id',post_id).execute(); return redirect(url_for('admin'))
@app.route('/admin/excluir/<post_id>',methods=['POST'])
@admin_required
def delete_post(post_id):
    p=sb.table('posts').select('*').eq('id',post_id).maybe_single().execute().data
    if p:
        if p.get('media_path'): sb.storage.from_(BUCKET).remove([p['media_path']])
        cs=sb.table('comments').select('*').eq('post_id',post_id).execute().data or []
        for c in cs:
            if c.get('audio'): sb.storage.from_(BUCKET).remove([c['audio']])
            rs=sb.table('replies').select('*').eq('comment_id',c['id']).execute().data or []
            for r in rs:
                if r.get('audio'): sb.storage.from_(BUCKET).remove([r['audio']])
        sb.table('posts').delete().eq('id',post_id).execute()
    return redirect(url_for('admin'))
@app.route('/admin/denuncia/<rid>',methods=['POST'])
@admin_required
def review_report(rid): sb.table('reports').update({'status':'reviewed'}).eq('id',rid).execute(); return redirect(url_for('admin'))

@app.errorhandler(403)
def forbidden(e): return page('Acesso negado','<div class="card"><h2>Acesso restrito</h2></div>'),403
@app.errorhandler(404)
def missing(e): return page('Não encontrado','<div class="card"><h2>Página não encontrada</h2></div>'),404
if __name__=='__main__': app.run(host='0.0.0.0',port=int(os.environ.get('PORT',5000)),debug=False)
