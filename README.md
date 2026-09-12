# NOTA

Sistema web de gestão de notas para o curso de Informática na Ótica do Utilizador.

## Arranque local

1. Crie um ambiente virtual e instale dependências:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

2. Copie `.env.example` para `.env` e altere `SECRET_KEY`, `ADMIN_PASSWORD` e `DATABASE_URL`. Para PostgreSQL, use por exemplo `postgresql+psycopg://utilizador:password@localhost:5432/nota_site`.

3. Crie o primeiro administrador e arranque:

```powershell
flask --app run.py create-admin
python run.py
```

Abra `http://127.0.0.1:5000/login`.

## Fluxo de teste

Entre com o administrador, crie um aluno em **Alunos**, lance quatro notas em **Lançar notas** e publique cada nota. O aluno entra com o utilizador/password criados e só vê notas publicadas da sua própria conta.

## Testes

```powershell
pytest -q
```

A aplicação inclui CSRF, cookies HTTP-only/SameSite, cabeçalhos de segurança, limite de 5 tentativas de login por minuto e limite de 5 MB por pedido. Em produção com vários workers, configure `RATELIMIT_STORAGE_URI` com um Redis partilhado para que o limite seja comum a todos os processos; sem essa variável, é usado armazenamento em memória por processo.

A aplicação cria as tabelas automaticamente no primeiro arranque. Em produção, use PostgreSQL, HTTPS (`SESSION_COOKIE_SECURE=true`), uma `SECRET_KEY` forte e uma ferramenta de migrações como Flask-Migrate/Alembic antes de alterar o esquema.

## Publicar no Render

Envie o projeto para um repositório GitHub e crie um Blueprint no Render usando `render.yaml`. O Blueprint cria o serviço web e o PostgreSQL persistente; confirme no painel do serviço que `DATABASE_URL` está configurada e que aponta para a base criada pelo Blueprint. Não use `sqlite:///nota_site.db` no serviço web do Render, porque esse ficheiro fica no disco temporário e pode desaparecer após um reinício ou novo deploy. O comando de arranque é `gunicorn --bind 0.0.0.0:$PORT run:app`. Depois do primeiro deploy, abra o Shell do serviço e execute `flask --app run.py create-admin --username admin`.
