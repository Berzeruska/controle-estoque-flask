"""Camada de serviços: regras de negócio, sem saber nada de HTTP.

As rotas (blueprints) só traduzem formulário -> chamada de serviço -> página.
Separar as camadas permite testar a regra sem subir servidor e trocar a
interface (uma API JSON, por exemplo) sem reescrever a lógica.
"""
