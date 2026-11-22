#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from pathlib import Path
import fitz
import pytest
import pikepdf


@pytest.fixture
def pdf_teste(tmp_path) -> Path:
    """Cria um PDF simples com 3 páginas para testes em tempo de execução."""
    caminho = tmp_path / "documento_teste.pdf"
    doc = fitz.open()
    for i in range(3):
        pagina = doc.new_page()
        pagina.insert_text((72, 72), f"Conteudo da pagina {i + 1} do processo judicial simulado.")
    doc.save(caminho)
    doc.close()
    return caminho


@pytest.fixture
def pdf_grande_teste(tmp_path) -> Path:
    """Cria um PDF maior com várias páginas para testes de fatiamento."""
    caminho = tmp_path / "documento_grande.pdf"
    doc = fitz.open()
    for i in range(25):
        pagina = doc.new_page()
        # Insere bastante texto simulado para ocupar espaço
        texto = f"Pagina {i + 1} " + "Texto repetido para simular tamanho de peticao. " * 50
        pagina.insert_text((50, 50), texto)
    doc.save(caminho)
    doc.close()
    return caminho
