#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Configuração centralizada de logs do projeto Gensai.
Registra apenas metadados operacionais (tempos, tamanhos e erros) em arquivo rotativo,
sem expor conteúdo dos documentos (LGPD) e sem poluir o terminal.
Licença: GNU GPLv3
"""

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path


def configurar_logger(nome: str = "gensai") -> logging.Logger:
    """Inicializa e retorna um logger que grava exclusivamente em logs/gensai.log."""
    logger = logging.getLogger(nome)

    # Evita duplicar handlers caso a função seja chamada mais de uma vez
    if logger.handlers:
        return logger

    logger.setLevel(logging.INFO)
    logger.propagate = False

    pasta_logs = Path(__file__).resolve().parent.parent / "logs"
    pasta_logs.mkdir(parents=True, exist_ok=True)
    arquivo_log = pasta_logs / "gensai.log"

    formato = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-8s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Handler de arquivo com rotação automática (2 MB por arquivo, até 3 backups)
    file_handler = RotatingFileHandler(
        arquivo_log,
        maxBytes=2 * 1024 * 1024,
        backupCount=3,
        encoding="utf-8",
    )
    file_handler.setFormatter(formato)
    file_handler.setLevel(logging.INFO)

    logger.addHandler(file_handler)

    return logger