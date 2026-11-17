"""Ponto de entrada.

    flask --app wsgi seed      # cria banco com dados de demonstração
    flask --app wsgi run       # sobe o servidor em http://127.0.0.1:5000
"""
import os

from app import create_app

app = create_app(os.getenv("APP_ENV", "dev"))

if __name__ == "__main__":
    app.run()
