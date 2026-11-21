#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Battousai — Motor de compressão paralela em DPI controlado e fatiamento exato de PDFs.
Licença: GNU GPLv3
"""

from concurrent.futures import ThreadPoolExecutor
import io
import os
import platform
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pikepdf
import fitz

from src.logger import configurar_logger

logger = configurar_logger("gensai")

# Perfis de resolução (DPI) e qualidade JPEG para compressão no Ghostscript
NIVEIS_COMPACTACAO = {
    "extrema": {"dpi": 120, "jpegq": 50, "preset": "/screen"},
    "boa":     {"dpi": 150, "jpegq": 65, "preset": "/ebook"},
    "razoavel": {"dpi": 200, "jpegq": 75, "preset": "/ebook"},
    "minima":  {"dpi": 300, "jpegq": 85, "preset": "/printer"},
}

LIMITES_MB = {
    "pje_trt": 1.5,
    "pje_2mb": 2.0,
    "pje_mg": 4.5,
    "sem_limite": 0.0,
}


def localizar_ghostscript() -> str:
    """Detecta automaticamente o executável do Ghostscript no Linux ou Windows."""
    sistema = platform.system()
    candidatos = ["gs"] if sistema != "Windows" else ["gswin64c", "gswin32c", "gs"]

    for comando in candidatos:
        caminho = shutil.which(comando)
        if caminho:
            return caminho

    erro = (
        "Ghostscript não encontrado no sistema. "
        "No Fedora, instale com: sudo dnf install ghostscript"
    )
    logger.error(erro)
    raise RuntimeError(erro)


def comprimir_pdf(
    caminho_entrada: Path,
    caminho_saida: Path,
    nivel: str = "boa",
    pdfa_versao: Optional[int] = 0,
    escala_cinza: bool = False,
    pagina_inicial: Optional[int] = None,
    pagina_final: Optional[int] = None,
) -> Path:
    """Comprime um PDF (ou uma faixa de páginas) usando Ghostscript."""
    if nivel not in NIVEIS_COMPACTACAO:
        raise ValueError(f"Nível inválido. Escolha entre: {list(NIVEIS_COMPACTACAO.keys())}")

    perfil = NIVEIS_COMPACTACAO[nivel]
    dpi = str(perfil["dpi"])
    jpegq = str(perfil["jpegq"])
    preset = str(perfil["preset"])
    gs_bin = localizar_ghostscript()

    comando = [
        gs_bin,
        "-sDEVICE=pdfwrite",
        "-dBATCH",
        "-dNOPAUSE",
        "-dSAFER",
        "-dNOOUTERSAVE",
        "-dQUIET",
        "-dUseFastColor=true",
        "-dFastWebView=false",
        f"-dPDFSETTINGS={preset}",
        "-dEmbedAllFonts=true",
        "-dSubsetFonts=true",
        "-dCompressFonts=true",
        "-dAutoRotatePages=/None",
        "-dDetectDuplicateImages=true",
        "-dDownsampleColorImages=true",
        "-dDownsampleGrayImages=true",
        "-dDownsampleMonoImages=true",
        "-dColorImageDownsampleType=/Average",
        "-dGrayImageDownsampleType=/Average",
        "-dMonoImageDownsampleType=/Subsample",
        f"-dJPEGQ={jpegq}",
        f"-dColorImageResolution={dpi}",
        f"-dGrayImageResolution={dpi}",
        f"-dMonoImageResolution={dpi}",
    ]

    if pdfa_versao in (1, 2):
        comando.extend([
            f"-dPDFA={pdfa_versao}",
            "-dPDFACompatibilityPolicy=1",
        ])

    if escala_cinza:
        comando.extend([
            "-sProcessColorModel=DeviceGray",
            "-sColorConversionStrategy=Gray",
            "-dOverrideICC",
        ])

    if pagina_inicial and pagina_final:
        comando.extend([
            f"-dFirstPage={pagina_inicial}",
            f"-dLastPage={pagina_final}",
        ])

    comando.extend([
        f"-sOutputFile={str(caminho_saida)}",
        str(caminho_entrada),
    ])

    resultado = subprocess.run(
        comando,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )

    if resultado.returncode != 0 or not caminho_saida.exists():
        logger.error("Falha no Ghostscript: %s", resultado.stderr.strip())
        raise RuntimeError(f"Falha ao executar Ghostscript: {resultado.stderr}")

    return caminho_saida


def vale_a_pena_comprimir(
    caminho_entrada: Path,
    nivel: str,
    pdfa: int,
    cinza: bool,
    amostra: int = 12,
) -> bool:
    """
    Comprime uma amostra distribuída de páginas e verifica se há redução real (>= 5%).
    Evita desperdiçar minutos em PDFs já otimizados.
    """
    t0 = time.perf_counter()
    with pikepdf.open(caminho_entrada) as origem:
        total = len(origem.pages)
        if total <= amostra:
            return True

        passo = max(1, total // amostra)
        indices = list(range(0, total, passo))[:amostra]

        with tempfile.TemporaryDirectory(prefix="gensai_amostra_") as tmp:
            tmp_dir = Path(tmp)
            orig_amostra = tmp_dir / "amostra_orig.pdf"
            comp_amostra = tmp_dir / "amostra_comp.pdf"

            fatia = pikepdf.Pdf.new()
            for i in indices:
                fatia.pages.append(origem.pages[i])
            fatia.remove_unreferenced_resources()
            fatia.save(orig_amostra)

            comprimir_pdf(orig_amostra, comp_amostra, nivel, pdfa, cinza)
            razao = comp_amostra.stat().st_size / max(1, orig_amostra.stat().st_size)

    tempo_amostra = time.perf_counter() - t0
    logger.info(
        "Teste de amostra (%d págs em %.2fs): Ghostscript resultou em %.0f%% do tamanho original.",
        len(indices),
        tempo_amostra,
        razao * 100,
    )
    return razao < 0.95


def comprimir_pdf_paralelo(
    caminho_entrada: Path,
    caminho_saida: Path,
    nivel: str = "boa",
    pdfa_versao: Optional[int] = 0,
    escala_cinza: bool = False,
    workers: Optional[int] = None,
) -> Path:
    """Comprime em blocos de páginas usando múltiplos processos Ghostscript em paralelo."""
    t0 = time.perf_counter()
    # Limita a 3 workers por padrão para manter o consumo de RAM seguro em máquinas de 8 GB
    workers = workers or min(3, os.cpu_count() or 2)

    with pikepdf.open(caminho_entrada) as p:
        total = len(p.pages)

    logger.info(
        "Iniciando Ghostscript paralelo (Nível: %s | PDF/A: %s | Cinza: %s | Workers: %d)...",
        nivel,
        pdfa_versao,
        escala_cinza,
        workers,
    )

    if workers <= 1 or total < 40:
        comprimir_pdf(caminho_entrada, caminho_saida, nivel, pdfa_versao, escala_cinza)
    else:
        n_blocos = workers * 2
        tam = -(-total // n_blocos)
        faixas = [(i + 1, min(i + tam, total)) for i in range(0, total, tam)]
        blocos = [caminho_saida.parent / f"bloco_{k}.pdf" for k in range(len(faixas))]

        with ThreadPoolExecutor(max_workers=workers) as ex:
            futuros = [
                ex.submit(
                    comprimir_pdf,
                    caminho_entrada,
                    bloco,
                    nivel,
                    pdfa_versao,
                    escala_cinza,
                    ini,
                    fim,
                )
                for bloco, (ini, fim) in zip(blocos, faixas)
            ]
            for f in futuros:
                f.result()

        abertos = [pikepdf.open(b) for b in blocos]
        try:
            with pikepdf.Pdf.new() as final:
                for a in abertos:
                    final.pages.extend(a.pages)
                final.save(
                    caminho_saida,
                    compress_streams=True,
                    object_stream_mode=pikepdf.ObjectStreamMode.generate,
                )
        finally:
            for a in abertos:
                a.close()

    tempo_gs = time.perf_counter() - t0
    tam_mb = caminho_saida.stat().st_size / (1024 * 1024)
    logger.info("Ghostscript finalizado em %.2fs (Tamanho comprimido: %.2f MB).", tempo_gs, tam_mb)
    return caminho_saida


def _bytes_parte(doc_origem: fitz.Document, inicio: int, fim: int) -> bytes:
    """Monta a fatia [inicio:fim) em memória com limpeza rápida de recursos em C."""
    doc_parte = fitz.open()
    doc_parte.insert_pdf(doc_origem, from_page=inicio, to_page=fim - 1)
    dados = doc_parte.tobytes(garbage=3, deflate=True)
    doc_parte.close()
    return dados

def _achar_fim(
    pdf_origem: pikepdf.Pdf,
    inicio: int,
    total: int,
    limite_bytes: int,
    palpite: int,
) -> Tuple[int, bytes]:
    """
    Encontra o maior índice absoluto 'fim' tal que [inicio:fim) caiba em limite_bytes.
    Parte de um palpite pela média de página, expande/recua exponencialmente e fecha com busca binária.
    """
    cache: Dict[int, bytes] = {}

    def cabe(qtd: int) -> bool:
        if qtd not in cache:
            cache[qtd] = _bytes_parte(pdf_origem, inicio, inicio + qtd)
        return len(cache[qtd]) <= limite_bytes

    restante = total - inicio
    n = max(1, min(palpite, restante))

    if cabe(n):
        lo, hi = n, restante + 1
        passo = max(1, n // 4)
        while lo < restante:
            tent = min(lo + passo, restante)
            if cabe(tent):
                lo, passo = tent, passo * 2
            else:
                hi = tent
                break
    else:
        lo, hi = 0, n
        passo = max(1, n // 4)
        while hi > 1:
            tent = max(1, hi - passo)
            if cabe(tent):
                lo = tent
                break
            hi, passo = tent, passo * 2

    while hi - lo > 1:
        meio = (lo + hi) // 2
        if cabe(meio):
            lo = meio
        else:
            hi = meio

    qtd_final = max(lo, 1)
    if qtd_final not in cache:
        cache[qtd_final] = _bytes_parte(pdf_origem, inicio, inicio + qtd_final)

    return inicio + qtd_final, cache[qtd_final]


def dividir_pdf_por_tamanho(
    caminho_pdf: Path,
    pasta_saida: Path,
    prefixo_nome: str,
    limite_mb: float,
) -> List[Path]:
    """
    Fatia um PDF em múltiplos arquivos respeitando o teto em MB com medição real em RAM.
    """
    # Folga de 2% para compatibilidade com portais que calculam MB em base decimal (1.000.000)
    limite_bytes = int(limite_mb * 1024 * 1024 * 0.98)
    tamanho_atual = caminho_pdf.stat().st_size

    if limite_bytes <= 0 or tamanho_atual <= limite_bytes:
        destino_unico = pasta_saida / f"{prefixo_nome}_gensai.pdf"
        shutil.copy2(caminho_pdf, destino_unico)
        logger.info(
            "Arquivo já está dentro do limite (%.2f MB). Salvo sem dividir.",
            tamanho_atual / (1024 * 1024),
        )
        return [destino_unico]

    logger.info("Iniciando fatiamento com medição exata (Limite: %.2f MB)...", limite_mb)
    t0 = time.perf_counter()

    arquivos_gerados: List[Path] = []
    parte_atual = 1

    with fitz.open(caminho_pdf) as pdf_origem:
        total_paginas = len(pdf_origem)
        media = tamanho_atual / max(1, total_paginas)
        palpite = max(1, int((limite_bytes * 0.95) / max(1, media)))
        logger.info("Total de páginas a fatiar: %d (palpite inicial: ~%d págs/parte)", total_paginas, palpite)

        inicio = 0
        while inicio < total_paginas:
            fim_abs, dados = _achar_fim(
                pdf_origem, inicio, total_paginas, limite_bytes, palpite
            )

            if len(dados) > limite_bytes:
                logger.warning(
                    "Página %d sozinha excede o limite (%.2f MB). Use compactação mais forte.",
                    inicio + 1,
                    len(dados) / (1024 * 1024),
                )

            caminho_parte = pasta_saida / f"{prefixo_nome}_parte_{parte_atual}.pdf"
            caminho_parte.write_bytes(dados)

            mb_parte = len(dados) / (1024 * 1024)
            logger.info(
                "Parte %d gerada: páginas %d a %d (%.2f MB).",
                parte_atual,
                inicio + 1,
                fim_abs,
                mb_parte,
            )

            arquivos_gerados.append(caminho_parte)
            inicio = fim_abs
            parte_atual += 1

    tempo_corte = time.perf_counter() - t0
    logger.info("Fatiamento concluído em %.2fs (%d partes geradas).", tempo_corte, len(arquivos_gerados))
    return arquivos_gerados


def executar_corte(
    entrada: str,
    pasta_saida: Optional[str] = None,
    nivel: str = "boa",
    limite_mb: float = 4.5,
    pdfa: int = 0,
    cinza: bool = False,
) -> List[Path]:
    """Fluxo completo (Privacy by Design / LGPD)."""
    t_total = time.perf_counter()
    caminho_entrada = Path(entrada).resolve()

    if not caminho_entrada.exists():
        logger.error("Arquivo de entrada não encontrado: %s", caminho_entrada.name)
        raise FileNotFoundError(f"Arquivo não encontrado: {caminho_entrada}")

    tam_orig_mb = caminho_entrada.stat().st_size / (1024 * 1024)
    logger.info("=== Iniciando Gensai/Battousai | Arquivo: '%s' (%.2f MB) ===", caminho_entrada.name, tam_orig_mb)

    destino = Path(pasta_saida).resolve() if pasta_saida else caminho_entrada.parent
    destino.mkdir(parents=True, exist_ok=True)
    prefixo = caminho_entrada.stem

    with tempfile.TemporaryDirectory(prefix="gensai_battousai_") as temp_dir:
        pdf_comprimido = Path(temp_dir) / "comprimido.pdf"

        if vale_a_pena_comprimir(caminho_entrada, nivel, pdfa, cinza):
            comprimir_pdf_paralelo(
                caminho_entrada=caminho_entrada,
                caminho_saida=pdf_comprimido,
                nivel=nivel,
                pdfa_versao=pdfa,
                escala_cinza=cinza,
            )

            if pdf_comprimido.stat().st_size > caminho_entrada.stat().st_size:
                logger.warning(
                    "PDF comprimido ficou maior que o original. Usando o arquivo original como base."
                )
                pdf_base = caminho_entrada
            else:
                pdf_base = pdf_comprimido
        else:
            logger.info("Ghostscript não reduz este PDF. Pulando compressão para ganhar velocidade.")
            pdf_base = caminho_entrada

        arquivos_finais = dividir_pdf_por_tamanho(
            caminho_pdf=pdf_base,
            pasta_saida=destino,
            prefixo_nome=prefixo,
            limite_mb=limite_mb,
        )

    tempo_total = time.perf_counter() - t_total
    tam_final_mb = sum(f.stat().st_size for f in arquivos_finais) / (1024 * 1024)
    logger.info(
        "=== Concluído em %.2fs | %.2f MB -> %.2f MB (%d arquivo(s)) ===",
        tempo_total,
        tam_orig_mb,
        tam_final_mb,
        len(arquivos_finais),
    )

    return arquivos_finais