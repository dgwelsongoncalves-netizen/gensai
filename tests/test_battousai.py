#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from pathlib import Path
import pytest

from src.battousai import (
    NIVEIS_COMPACTACAO,
    localizar_ghostscript,
    dividir_pdf_por_tamanho,
    executar_corte,
)


def test_niveis_compactacao_existem():
    assert "boa" in NIVEIS_COMPACTACAO
    assert "extrema" in NIVEIS_COMPACTACAO
    assert "minima" in NIVEIS_COMPACTACAO


def test_localizar_ghostscript_retorna_string_ou_levanta():
    try:
        gs = localizar_ghostscript()
        assert isinstance(gs, str)
        assert len(gs) > 0
    except RuntimeError as e:
        # Se Ghostscript não estiver instalado no ambiente de CI/container, o erro deve mencionar o dnf/instalação
        assert "Ghostscript não encontrado" in str(e)


def test_dividir_pdf_por_tamanho_pequeno(pdf_teste, tmp_path):
    """PDF pequeno que cabe inteiro no limite não deve ser fatiado em múltiplos arquivos."""
    pasta_saida = tmp_path / "saida"
    pasta_saida.mkdir()

    arquivos = dividir_pdf_por_tamanho(
        caminho_pdf=pdf_teste,
        pasta_saida=pasta_saida,
        prefixo_nome="teste_pequeno",
        limite_mb=10.0,
    )

    assert len(arquivos) == 1
    assert arquivos[0].exists()
    assert arquivos[0].name.endswith("_gensai.pdf")


def test_executar_corte_arquivo_inexistente():
    with pytest.raises(FileNotFoundError):
        executar_corte(entrada="arquivo_que_nao_existe_12345.pdf")
