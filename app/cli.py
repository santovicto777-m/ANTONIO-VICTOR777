import click
from flask.cli import with_appcontext

from app import db
from app.models import User


def register_commands(app):
    @app.cli.command("create-admin")
    @click.option("--username", prompt="Utilizador")
    @click.option("--password", prompt=True, hide_input=True, confirmation_prompt=True)
    @with_appcontext
    def create_admin(username, password):
        if User.query.filter_by(username=username).first():
            raise click.ClickException("Esse utilizador já existe.")
        user = User(username=username, role="admin")
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        click.echo("Administrador criado.")

    @app.cli.command("reset-admin-password")
    @click.option("--username", default="admin", show_default=True)
    @click.option("--password", prompt=True, hide_input=True, confirmation_prompt=True)
    @with_appcontext
    def reset_admin_password(username, password):
        user = User.query.filter_by(username=username, role="admin").first()
        if not user:
            raise click.ClickException("Administrador não encontrado.")
        if len(password) < 8:
            raise click.ClickException("A palavra-passe deve ter pelo menos 8 caracteres.")
        user.set_password(password)
        user.active = True
        db.session.commit()
        click.echo("Palavra-passe do administrador redefinida e conta ativada.")

    @app.cli.command("activate-admin")
    @click.option("--username", default="admin", show_default=True)
    @with_appcontext
    def activate_admin(username):
        user = User.query.filter_by(username=username, role="admin").first()
        if not user:
            raise click.ClickException("Administrador não encontrado.")
        user.active = True
        db.session.commit()
        click.echo(f"Administrador {username} ativado.")
