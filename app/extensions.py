"""Extensões compartilhadas.

Ficam num módulo próprio para evitar importação circular: os modelos
importam `db` daqui, e a fábrica da aplicação também — sem que um precise
importar o outro.
"""
from flask_sqlalchemy import SQLAlchemy
from flask_wtf import CSRFProtect
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


db = SQLAlchemy(model_class=Base)
csrf = CSRFProtect()
