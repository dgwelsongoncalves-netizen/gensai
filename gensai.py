#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Gensai — Otimizador e Divisor de PDFs para Sistemas Judiciais (PJe/eproc/Projudi).
Motor principal: Battousai (src/battousai.py)
Licença: GNU GPLv3
"""

import argparse
import sys
from pathlib import Path

from src.battousai import NIVEIS_COMPACTACAO, executar_corte
from src.logger import configurar_logger

__version__ = "0.2.1"
logger = configurar_logger("gensai")


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="gensai",
        description="Gensai — Compressão e fatiamento preciso de PDFs para peticionamento eletrônico.",
    )
    parser.add_argument("entrada", help="Caminho do arquivo PDF original.")
    parser.add_argument(
        "-o", "--saida", help="Pasta de destino (padrão: mesma pasta do arquivo original)."
    )
    parser.add_argument(
        "-n",
        "--nivel",
        choices=list(NIVEIS_COMPACTACAO.keys()),
        default="boa",
        help="Nível de compactação em DPI (padrão: boa - 150 DPI).",
    )
    parser.add_argument(
        "-l",
        "--limite",
        type=float,
        default=4.5,
        help="Tamanho máximo por arquivo em MB (ex: 1.5, 2.0, 4.5). Use 0 para não dividir.",
    )
    parser.add_argument(
        "--pdfa",
        type=int,
        choices=[0, 1, 2],
        default=1,
        help="Versão PDF/A (1 para PDF/A-1b, 2 para PDF/A-2b, 0 para desativar).",
    )
    parser.add_argument(
        "--cinza",
        action="store_true",
        help="Converte o documento para escala de cinza (reduz ainda mais o tamanho).",
    )

    args = parser.parse_args()

    try:
        resultados = executar_corte(
            entrada=args.entrada,
            pasta_saida=args.saida,
            nivel=args.nivel,
            limite_mb=args.limite,
            pdfa=args.pdfa,
            cinza=args.cinza,
        )

        tamanho_orig_mb = Path(args.entrada).stat().st_size / (1024 * 1024)
        tamanho_final_mb = sum(f.stat().st_size for f in resultados) / (1024 * 1024)
        reducao = (1 - (tamanho_final_mb / tamanho_orig_mb)) * 100 if tamanho_orig_mb > 0 else 0

        print(f"\nResumo: {tamanho_orig_mb:.2f} MB -> {tamanho_final_mb:.2f} MB ({reducao:.1f}% de redução)")
        for arq in resultados:
            mb = arq.stat().st_size / (1024 * 1024)
            print(f"  - {arq.name} ({mb:.2f} MB)")

    except Exception as exc:
        logger.exception("Erro fatal durante a execução do Gensai: %s", exc)
        sys.exit(1)


if __name__ == "__main__":
    main()