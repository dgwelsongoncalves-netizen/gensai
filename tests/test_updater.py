#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import pytest
from src.updater import _parse_versao, verificar_atualizacao


def test_parse_versao():
    assert _parse_versao("v1.2.0") == (1, 2, 0)
    assert _parse_versao("1.2.0") == (1, 2, 0)
    assert _parse_versao("v2.1") == (2, 1)
    assert _parse_versao("v1.2.3-beta") == (1, 2, 3, 0) or _parse_versao("v1.2.3-beta") == (1, 2, 0)



def test_verificar_atualizacao_sem_atualizacao(monkeypatch):
    class MockResponse:
        status_code = 200
        def json(self):
            return {"tag_name": "v0.1.0", "assets": []}

    monkeypatch.setattr("requests.get", lambda *args, **kwargs: MockResponse())
    resultado = verificar_atualizacao("0.2.0")
    assert resultado is None


def test_verificar_atualizacao_com_nova_versao(monkeypatch):
    class MockResponse:
        status_code = 200
        def json(self):
            return {
                "tag_name": "v1.0.0",
                "html_url": "https://github.com/test/release",
                "assets": [{"name": "gensai-setup.exe", "browser_download_url": "https://github.com/test/download.exe"}]
            }

    monkeypatch.setattr("requests.get", lambda *args, **kwargs: MockResponse())
    resultado = verificar_atualizacao("0.2.0")
    assert resultado is not None
    assert resultado["versao"] == "1.0.0"
    assert resultado["url_download"] == "https://github.com/test/download.exe"


def test_verificar_atualizacao_erro_rede(monkeypatch):
    def mock_get(*args, **kwargs):
        raise Exception("Erro de conexão")

    monkeypatch.setattr("requests.get", mock_get)
    resultado = verificar_atualizacao("0.2.0")
    assert resultado is None
