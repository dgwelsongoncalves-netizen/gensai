#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import logging
from pathlib import Path
import pytest

from src.logger import configurar_logger


def test_configurar_logger_cria_arquivo_e_handler(tmp_path, monkeypatch):
    """
    Testa se o configurador de logger inicializa corretamente,
    evita handlers duplicados e grava no arquivo de log esperado usando tmp_path.
    """
    fake_logs_dir = tmp_path / "logs"
    
    # Mocka a construção do caminho no Path dentro de src.logger
    class FakePath:
        def __init__(self, *args, **kwargs):
            pass
        def resolve(self):
            return self
        @property
        def parent(self):
            return FakeParent()

    class FakeParent:
        @property
        def parent(self):
            return fake_logs_dir

    import src.logger as logger_module
    monkeypatch.setattr(logger_module, "Path", lambda *args: fake_logs_dir / "dummy")

    logger_nome = "test_gensai_logger"
    logger = logging.getLogger(logger_nome)
    logger.handlers.clear()

    criado = configurar_logger(logger_nome)

    assert isinstance(criado, logging.Logger)
    assert criado.level == logging.INFO
    assert not criado.propagate
    assert len(criado.handlers) == 1

    # Testa chamada repetida (singleton / sem duplicar handlers)
    criado_denovo = configurar_logger(logger_nome)
    assert len(criado_denovo.handlers) == 1

