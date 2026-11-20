#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Battousai — Motor de compressão em DPI controlado e fatiamento de PDFs do projeto Gensai.
Licença: GNU GPLv3
"""

import io
import os
import platform
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from typing import List, Optional

import pikepdf

from src.logger import configurar_logger

logger = configurar_logger("gensai")

# Perfis de resolução (DPI) e qualidade JPEG para compressão real no Ghostscript
NIVEIS_COMPACTACAO = {
    "extrema": {"dpi": 120, "jpegq": 50, "preset": "/screen"},
    "boa":     {"dpi": 150, "jpegq": 65, "preset": "/ebook"},
    "razoavel": {"dpi": 200, "jpegq": 75, "preset": "/ebook"},
    "minima":  {"dpi": 300, "jpegq": 85, "preset": "/printer"},
}

# Perfis pré-definidos de tamanho máximo em Megabytes (com margem de segurança)
LIMITES_MB = {
    "pje_trt": 1.5,
    "pje_2mb": 2.0,
    "pje_mg": 4.5,    # Margem segura para o teto de 5 MB do PJe
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
    pdfa_versao: Optional[int] = 1,
    escala_cinza: bool = False,
) -> Path:
    """
    Comprime um PDF usando Ghostscript com reamostragem rápida (/Average),
    multi-threading, compressão JPEG controlada e conformidade opcional com PDF/A.
    """
    if nivel not in NIVEIS_COMPACTACAO:
        raise ValueError(f"Nível inválido. Escolha entre: {list(NIVEIS_COMPACTACAO.keys())}")

    perfil = NIVEIS_COMPACTACAO[nivel]
    dpi = str(perfil["dpi"])
    jpegq = str(perfil["jpegq"])
    preset = str(perfil["preset"])
    gs_bin = localizar_ghostscript()
    threads = str(max(1, os.cpu_count() or 2))

    comando = [
        gs_bin,
        "-sDEVICE=pdfwrite",
        "-dBATCH",
        "-dNOPAUSE",
        "-dSAFER",
        "-dNOOUTERSAVE",
        "-dQUIET",
        f"-dNumRenderingThreads={threads}",
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
        "-dAutoFilterColorImages=false",
        "-dColorImageFilter=/DCTEncode",
        "-dAutoFilterGrayImages=false",
        "-dGrayImageFilter=/DCTEncode",
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

    comando.extend([
        f"-sOutputFile={str(caminho_saida)}",
        str(caminho_entrada),
    ])

    logger.info(
        "Iniciando Ghostscript (Nível: %s | DPI: %s | PDF/A: %s | Cinza: %s | Threads: %s)...",
        nivel,
        dpi,
        pdfa_versao,
        escala_cinza,
        threads,
    )
    t0 = time.perf_counter()

    resultado = subprocess.run(
        comando,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )

    tempo_gs = time.perf_counter() - t0

    if resultado.returncode != 0 or not caminho_saida.exists():
        logger.error("Falha no Ghostscript (%.2fs): %s", tempo_gs, resultado.stderr.strip())
        raise RuntimeError(f"Falha ao executar Ghostscript: {resultado.stderr}")

    tam_mb = caminho_saida.stat().st_size / (1024 * 1024)
    logger.info("Ghostscript finalizado em %.2fs (Tamanho comprimido: %.2f MB).", tempo_gs, tam_mb)
    return caminho_saida


def _medir_intervalo_em_memoria(pdf_origem: pikepdf.Pdf, inicio: int, fim: int) -> int:
    """
    Mede o tamanho aproximado de um bloco sequencial [inicio : fim] em RAM (io.BytesIO).
    Usa salvamento rápido (sem recompactar object streams) para acelerar a busca.
    """
    pdf_temp = pikepdf.Pdf.new()
    for i in range(inicio, fim):
        pdf_temp.pages.append(pdf_origem.pages[i])

    # Remove recursos órfãos para evitar falso estouro de limite
    pdf_temp.remove_unreferenced_resources()

    with io.BytesIO() as buffer:
        pdf_temp.save(
            buffer,
            compress_streams=False,
            object_stream_mode=pikepdf.ObjectStreamMode.preserve,
        )
        return buffer.getbuffer().nbytes


def dividir_pdf_por_tamanho(
    caminho_pdf: Path,
    pasta_saida: Path,
    prefixo_nome: str,
    limite_mb: float,
) -> List[Path]:
    """
    Fatia um PDF em múltiplos arquivos respeitando o teto em MB.
    Utiliza Busca Exponencial (Galloping) + Busca Binária restrita em RAM (io.BytesIO)
    para encontrar o ponto exato de corte com alta velocidade e ordem 100% preservada.
    """
    limite_bytes = int(limite_mb * 1024 * 1024)
    tamanho_atual = caminho_pdf.stat().st_size

    if limite_bytes <= 0 or tamanho_atual <= limite_bytes:
        destino_unico = pasta_saida / f"{prefixo_nome}_gensai.pdf"
        shutil.copy2(caminho_pdf, destino_unico)
        logger.info(
            "Arquivo já está dentro do limite (%.2f MB). Salvo sem dividir.",
            tamanho_atual / (1024 * 1024),
        )
        return [destino_unico]

    logger.info("Iniciando fatiamento otimizado (Limite: %.2f MB)...", limite_mb)
    t0 = time.perf_counter()

    arquivos_gerados: List[Path] = []
    parte_atual = 1

    with pikepdf.open(caminho_pdf) as pdf_origem:
        total_paginas = len(pdf_origem.pages)
        logger.info("Total de páginas a fatiar: %d", total_paginas)
        inicio = 0

        while inicio < total_paginas:
            if inicio == total_paginas - 1:
                melhor_fim = total_paginas
            else:
                # 1. Busca Exponencial (Galloping): acha rapidamente o teto sem testar o PDF inteiro
                salto = 8
                baixo = inicio + 1
                alto = min(inicio + salto, total_paginas)
                melhor_fim = inicio + 1

                while alto <= total_paginas:
                    tamanho_teste = _medir_intervalo_em_memoria(pdf_origem, inicio, alto)
                    if tamanho_teste <= limite_bytes:
                        melhor_fim = alto
                        baixo = alto + 1
                        if alto == total_paginas:
                            break
                        salto *= 2
                        alto = min(inicio + salto, total_paginas)
                    else:
                        alto -= 1
                        break

                # 2. Busca Binária restrita apenas ao intervalo curto [baixo, alto]
                while baixo <= alto:
                    meio = (baixo + alto) // 2
                    tamanho_teste = _medir_intervalo_em_memoria(pdf_origem, inicio, meio)

                    if tamanho_teste <= limite_bytes:
                        melhor_fim = meio
                        baixo = meio + 1
                    else:
                        alto = meio - 1

            # Grava apenas o arquivo final desta parte no disco (com compressão completa)
            pdf_parte = pikepdf.Pdf.new()
            for i in range(inicio, melhor_fim):
                pdf_parte.pages.append(pdf_origem.pages[i])

            pdf_parte.remove_unreferenced_resources()
            caminho_parte = pasta_saida / f"{prefixo_nome}_parte_{parte_atual}.pdf"
            pdf_parte.save(
                caminho_parte,
                compress_streams=True,
                object_stream_mode=pikepdf.ObjectStreamMode.generate,
            )

            tamanho_bytes = caminho_parte.stat().st_size
            if tamanho_bytes == 0:
                erro = f"Erro de integridade: '{caminho_parte.name}' foi gerado com 0 bytes."
                logger.error(erro)
                raise RuntimeError(erro)

            mb_parte = tamanho_bytes / (1024 * 1024)
            logger.info(
                "Parte %d gerada: páginas %d a %d (%.2f MB).",
                parte_atual,
                inicio + 1,
                melhor_fim,
                mb_parte,
            )

            arquivos_gerados.append(caminho_parte)
            inicio = melhor_fim
            parte_atual += 1

    tempo_corte = time.perf_counter() - t0
    logger.info("Fatiamento concluído em %.2fs (%d partes geradas).", tempo_corte, len(arquivos_gerados))
    return arquivos_gerados


def executar_corte(
    entrada: str,
    pasta_saida: Optional[str] = None,
    nivel: str = "boa",
    limite_mb: float = 4.5,
    pdfa: int = 1,
    cinza: bool = False,
) -> List[Path]:
    """
    Fluxo completo (Privacy by Design / LGPD):
    1. Comprime o PDF em diretório temporário isolado.
    2. Compara com o original: se não houver ganho, evita inchaço usando o menor arquivo.
    3. Divide automaticamente caso ultrapasse o limite_mb definido.
    4. Remove todos os arquivos temporários ao encerrar o bloco.
    """
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

        comprimir_pdf(
            caminho_entrada=caminho_entrada,
            caminho_saida=pdf_comprimido,
            nivel=nivel,
            pdfa_versao=pdfa,
            escala_cinza=cinza,
        )

        # Trava de segurança: se o arquivo comprimido ficou maior que o original, usa o original
        if pdf_comprimido.stat().st_size > caminho_entrada.stat().st_size:
            logger.warning(
                "PDF comprimido ficou maior que o original. Usando o arquivo original como base para o corte."
            )
            pdf_base = caminho_entrada
        else:
            pdf_base = pdf_comprimido

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