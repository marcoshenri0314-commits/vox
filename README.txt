# VOX — protótipo 2.0

Rede social experimental em que as publicações são áudios.

## Executar no computador
1. Instale Python 3.10 ou superior.
2. No terminal, dentro desta pasta, execute: `pip install -r requirements.txt`
3. Execute: `python app.py`
4. Abra `http://127.0.0.1:5000` no navegador.

## Recursos
- Feed público de áudios
- Upload de arquivos de áudio
- Gravação pelo microfone do navegador (quando suportada)
- Prévia da gravação antes de publicar
- Curtidas
- Banco SQLite local

## Importante
Este é um protótipo local. Para que outras pessoas acessem pela internet, será necessário hospedar a aplicação, configurar HTTPS, autenticação, proteção contra abuso, moderação, backups e armazenamento apropriado. O acesso ao microfone normalmente exige HTTPS ou localhost.
O limite técnico atual de upload é 512 MB por arquivo; não há limite de duração definido pelo aplicativo, mas arquivos maiores podem esbarrar em limites do servidor e do dispositivo.
Antes de publicar na internet, troque `app.secret_key` por uma chave secreta forte e implemente contas de usuário.
