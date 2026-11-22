#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from pathlib import Path
import sys
import pytest

from gensai import main


def test_cli_ajuda(monkeypatch, capsys):
    """Testa se a CLI exibe a ajuda sem erros ao passar --help."""
    monkeypatch.setattr(sys, "argv", ["gensai.py", "--help"])
    with pytest.raises(SystemExit) as exc_info:
        main()
    assert exc_info.value.code == 0
    
    captured = capsys.readouterr()
    assert "Gensai" in captured.out or "Gensai" in captured.err or "usage" in captured.out.lower()


def test_cli_arquivo_inexistente(monkeypatch):
    """Testa se a CLI encerra com código 1 ao receber um arquivo PDF inexistente."""
    monkeypatch.setattr(sys, "argv", ["gensai.py", "inexistente_999.pdf"])
    with pytest.raises(SystemExit) as exc_info:
        main()
    assert exc_info.value.code == 1
