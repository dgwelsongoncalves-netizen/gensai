#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Verificador automático de atualizações via GitHub Releases para o projeto Gensai.
Licença: GNU GPLv3
"""

from typing import Dict, Optional, Tuple

import requests

from src.logger import configurar_logger

logger = configurar_logger("gensai")

GITHUB_RELEASES_API = (
    "https://api.github.com/repos/dgwelsongoncalves-netizen/gensai/releases/latest"
)


def _parse_versao(tag: str) -> Tuple[int, ...]:
    """Converte uma tag de versão (ex: 'v1.2.0' ou '1.2.0') em tupla comparável."""
    limpa = tag.strip().lstrip("vV")
    partes = []
    for trecho in limpa.split("."):
        try:
            partes.append(int(trecho))
        except ValueError:
            partes.append(0)
    return tuple(partes)


def verificar_atualizacao(versao_atual: str, timeout: int = 5) -> Optional[Dict[str, str]]:
    """
    Consulta a última Release no GitHub.
    Retorna um dicionário com 'versao' e 'url_download' caso haja versão mais nova,
    ou None se já estiver atualizado ou sem conexão.
    """
    try:
        resposta = requests.get(
            GITHUB_RELEASES_API,
            headers={"Accept": "application/vnd.github+json"},
            timeout=timeout,
        )
        if resposta.status_code != 200:
            return None

        dados = resposta.json()
        tag_remota = dados.get("tag_name", "")
        if not tag_remota:
            return None

        if _parse_versao(tag_remota) > _parse_versao(versao_atual):
            url_destino = dados.get("html_url", "")
            # Prioriza o link direto do instalador Windows (.exe), se existir nos assets
            for asset in dados.get("assets", []):
                nome_asset = asset.get("name", "").lower()
                if nome_asset.endswith(".exe"):
                    url_destino = asset.get("browser_download_url", url_destino)
                    break

            logger.info("Nova versão disponível no GitHub: %s", tag_remota)
            return {
                "versao": tag_remota.lstrip("vV"),
                "url_download": url_destino,
            }
    except Exception as exc:
        logger.warning("Não foi possível verificar atualizações no GitHub: %s", exc)

    return None