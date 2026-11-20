#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Interface Gráfica (PySide6) do projeto Gensai.
Licença: GNU GPLv3
"""

import os
import platform
import subprocess
import sys
import webbrowser
from pathlib import Path
from typing import Dict, List, Optional

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QDragEnterEvent, QDropEvent, QIcon, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from gensai import __version__
from src.battousai import executar_corte
from src.logger import configurar_logger
from src.updater import verificar_atualizacao

logger = configurar_logger("gensai")


def caminho_recurso(relativo: str) -> Path:
    """Resolve caminhos de recursos (ícones/assets) tanto em dev quanto no PyInstaller."""
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    return base / relativo


class UpdaterWorker(QThread):
    """Thread em segundo plano para checar atualizações no GitHub sem travar a abertura."""

    atualizacao_encontrada = Signal(dict)

    def run(self) -> None:
        info = verificar_atualizacao(__version__)
        if info:
            self.atualizacao_encontrada.emit(info)


class BattousaiWorker(QThread):
    """Thread dedicada para executar o motor Battousai sem congelar a interface."""

    concluido = Signal(list, float)
    erro = Signal(str)

    def __init__(
        self,
        entrada: str,
        pasta_saida: Optional[str],
        nivel: str,
        limite_mb: float,
        pdfa: int,
        cinza: bool,
    ) -> None:
        super().__init__()
        self.entrada = entrada
        self.pasta_saida = pasta_saida
        self.nivel = nivel
        self.limite_mb = limite_mb
        self.pdfa = pdfa
        self.cinza = cinza

    def run(self) -> None:
        try:
            tamanho_orig_mb = Path(self.entrada).stat().st_size / (1024 * 1024)
            arquivos = executar_corte(
                entrada=self.entrada,
                pasta_saida=self.pasta_saida,
                nivel=self.nivel,
                limite_mb=self.limite_mb,
                pdfa=self.pdfa,
                cinza=self.cinza,
            )
            self.concluido.emit(arquivos, tamanho_orig_mb)
        except Exception as exc:
            logger.exception("Erro no processamento via GUI: %s", exc)
            self.erro.emit(str(exc))


class AreaDropPDF(QFrame):
    """Área interativa para arrastar e soltar ou clicar no botão para escolher um PDF."""

    arquivo_selecionado = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        self.setAcceptDrops(True)
        self.setObjectName("AreaDrop")
        self.setMinimumHeight(125)

        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(8)

        self.label_titulo = QLabel("Arraste o PDF processual aqui")
        self.label_titulo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.label_titulo.setStyleSheet("font-size: 14px; font-weight: bold; color: #F1F5F9;")

        self.btn_procurar = QPushButton("Procurar PDF no computador...")
        self.btn_procurar.setObjectName("BtnProcurar")
        self.btn_procurar.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_procurar.setMaximumWidth(240)
        self.btn_procurar.clicked.connect(self.abrir_seletor_arquivo)

        self.label_arquivo = QLabel("Nenhum arquivo selecionado")
        self.label_arquivo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.label_arquivo.setStyleSheet("font-size: 12px; color: #94A3B8;")

        layout.addWidget(self.label_titulo)
        layout.addWidget(self.btn_procurar, alignment=Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.label_arquivo)

    def abrir_seletor_arquivo(self) -> None:
        caminho, _ = QFileDialog.getOpenFileName(
            self,
            "Selecionar arquivo PDF para otimizar",
            str(Path.home() / "Documentos"),
            "Documentos PDF (*.pdf *.PDF);;Todos os arquivos (*)",
        )
        if caminho:
            self.definir_arquivo(caminho)

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:  # noqa: N802
        if event.mimeData().hasUrls():
            for url in event.mimeData().urls():
                if url.toLocalFile().lower().endswith(".pdf"):
                    event.acceptProposedAction()
                    return
        event.ignore()

    def dropEvent(self, event: QDropEvent) -> None:  # noqa: N802
        for url in event.mimeData().urls():
            caminho = url.toLocalFile()
            if caminho.lower().endswith(".pdf"):
                self.definir_arquivo(caminho)
                return

    def definir_arquivo(self, caminho: str) -> None:
        p = Path(caminho)
        tam_mb = p.stat().st_size / (1024 * 1024)
        self.label_arquivo.setText(f"Selecionado: {p.name} ({tam_mb:.2f} MB)")
        self.label_arquivo.setStyleSheet("font-size: 12px; color: #38BDF8; font-weight: bold;")
        self.arquivo_selecionado.emit(str(p))


class JanelaGensai(QMainWindow):
    """Janela principal do Gensai PDF."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(f"Gensai PDF v{__version__} — Motor Battousai")
        self.setMinimumSize(660, 660)

        self._carregar_icone_janela()

        self.arquivo_entrada: Optional[str] = None
        self.ultima_pasta_saida: Optional[Path] = None
        self.url_atualizacao: Optional[str] = None
        self.worker: Optional[BattousaiWorker] = None

        self._construir_interface()
        self._aplicar_estilo()
        self._checar_atualizacoes()

    def _carregar_icone_janela(self) -> None:
        for candidato in ("assets/gensai.ico", "assets/logo.png"):
            caminho = caminho_recurso(candidato)
            if caminho.exists():
                self.setWindowIcon(QIcon(str(caminho)))
                break

    def _construir_interface(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setSpacing(14)
        layout.setContentsMargins(20, 18, 20, 18)

        # Banner oculto de atualização automática (GitHub Releases)
        self.banner_update = QFrame()
        self.banner_update.setObjectName("BannerUpdate")
        self.banner_update.setVisible(False)
        lay_up = QHBoxLayout(self.banner_update)
        self.lbl_update = QLabel("")
        self.btn_baixar_update = QPushButton("Baixar atualização")
        self.btn_baixar_update.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_baixar_update.clicked.connect(self._abrir_link_atualizacao)
        lay_up.addWidget(self.lbl_update, 1)
        lay_up.addWidget(self.btn_baixar_update)
        layout.addWidget(self.banner_update)

        # Cabeçalho com Logo da Katana + Título
        lay_header = QHBoxLayout()
        lay_header.setSpacing(14)

        caminho_logo = caminho_recurso("assets/logo.png")
        if caminho_logo.exists():
            lbl_logo = QLabel()
            pixmap = QPixmap(str(caminho_logo))
            lbl_logo.setPixmap(
                pixmap.scaled(
                    130,
                    72,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
            )
            lbl_logo.setStyleSheet("border-radius: 6px;")
            lay_header.addWidget(lbl_logo)

        lay_titulos = QVBoxLayout()
        lay_titulos.setSpacing(2)
        titulo = QLabel("GENSAI PDF")
        titulo.setStyleSheet("font-size: 22px; font-weight: 800; color: #F8FAFC; letter-spacing: 1px;")
        subtitulo = QLabel(
            "Compressão local em DPI controlado e fatiamento seguro para PJe, eproc e Projudi (LGPD)"
        )
        subtitulo.setWordWrap(True)
        subtitulo.setStyleSheet("font-size: 12px; color: #94A3B8;")
        lay_titulos.addWidget(titulo)
        lay_titulos.addWidget(subtitulo)
        lay_header.addLayout(lay_titulos, 1)

        layout.addLayout(lay_header)

        # Área de Arrastar e Soltar + Botão de Selecionar PDF
        self.area_drop = AreaDropPDF()
        self.area_drop.arquivo_selecionado.connect(self._ao_selecionar_arquivo)
        layout.addWidget(self.area_drop)

        # Pasta de destino
        lay_pasta = QHBoxLayout()
        lbl_pasta = QLabel("Pasta de saída:")
        lbl_pasta.setMinimumWidth(105)
        self.input_pasta = QLineEdit()
        self.input_pasta.setPlaceholderText("Mesma pasta do arquivo original")
        self.input_pasta.setReadOnly(True)
        btn_pasta = QPushButton("Alterar pasta...")
        btn_pasta.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_pasta.clicked.connect(self._selecionar_pasta_saida)
        lay_pasta.addWidget(lbl_pasta)
        lay_pasta.addWidget(self.input_pasta, 1)
        lay_pasta.addWidget(btn_pasta)
        layout.addLayout(lay_pasta)

        # Nível de compactação
        lay_nivel = QHBoxLayout()
        lbl_nivel = QLabel("Compactação:")
        lbl_nivel.setMinimumWidth(105)
        self.combo_nivel = QComboBox()
        self.combo_nivel.addItem("Boa — 150 DPI (Recomendado para PJe)", "boa")
        self.combo_nivel.addItem("Extrema — 120 DPI (Máxima redução)", "extrema")
        self.combo_nivel.addItem("Razoável — 200 DPI (Documentos detalhados)", "razoavel")
        self.combo_nivel.addItem("Mínima — 300 DPI (Alta fidelidade)", "minima")
        lay_nivel.addWidget(lbl_nivel)
        lay_nivel.addWidget(self.combo_nivel, 1)
        layout.addLayout(lay_nivel)

        # Limite de tamanho por parte (botões rápidos + valor exato)
        lbl_lim = QLabel("Limite máximo por arquivo (MB):")
        lbl_lim.setStyleSheet("font-weight: bold; color: #CBD5E1;")
        layout.addWidget(lbl_lim)

        lay_botoes_lim = QHBoxLayout()
        self.grupo_limites = QButtonGroup(self)
        perfis = [
            ("1,5 MB (TRT)", 1.5),
            ("2,0 MB", 2.0),
            ("4,5 MB (PJe/TJMG)", 4.5),
            ("Sem dividir", 0.0),
        ]
        for texto, valor in perfis:
            btn = QPushButton(texto)
            btn.setCheckable(True)
            btn.setObjectName("BtnPerfil")
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            if valor == 4.5:
                btn.setChecked(True)
            btn.clicked.connect(lambda _checked, v=valor: self.spin_limite.setValue(v))
            self.grupo_limites.addButton(btn)
            lay_botoes_lim.addWidget(btn)

        self.spin_limite = QDoubleSpinBox()
        self.spin_limite.setRange(0.0, 100.0)
        self.spin_limite.setSingleStep(0.5)
        self.spin_limite.setDecimals(1)
        self.spin_limite.setSuffix(" MB")
        self.spin_limite.setValue(4.5)
        lay_botoes_lim.addWidget(self.spin_limite)
        layout.addLayout(lay_botoes_lim)

        # Opções adicionais (PDF/A e Escala de Cinza)
        lay_opcoes = QHBoxLayout()
        self.chk_pdfa = QCheckBox("Converter para padrão PDF/A-1b")
        self.chk_pdfa.setChecked(True)
        self.chk_cinza = QCheckBox("Converter para escala de cinza (mais leve)")
        lay_opcoes.addWidget(self.chk_pdfa)
        lay_opcoes.addWidget(self.chk_cinza)
        lay_opcoes.addStretch()
        layout.addLayout(lay_opcoes)

        # Botão Principal + Barra de Progresso
        self.btn_executar = QPushButton("Executar Corte (Battousai)")
        self.btn_executar.setObjectName("BtnExecutar")
        self.btn_executar.setMinimumHeight(44)
        self.btn_executar.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_executar.clicked.connect(self._iniciar_processamento)
        layout.addWidget(self.btn_executar)

        self.progresso = QProgressBar()
        self.progresso.setRange(0, 100)
        self.progresso.setValue(0)
        self.progresso.setTextVisible(False)
        self.progresso.setFixedHeight(8)
        layout.addWidget(self.progresso)

        # Área de resultado
        self.txt_resultado = QTextEdit()
        self.txt_resultado.setReadOnly(True)
        self.txt_resultado.setPlaceholderText("O resumo do corte e os arquivos gerados aparecerão aqui.")
        self.txt_resultado.setMinimumHeight(110)
        layout.addWidget(self.txt_resultado, 1)

        # Rodapé com botão Abrir Pasta
        lay_rodape = QHBoxLayout()
        self.lbl_status = QLabel("Pronto. Processamento 100% local.")
        self.lbl_status.setStyleSheet("color: #94A3B8; font-size: 12px;")
        self.btn_abrir_pasta = QPushButton("Abrir Pasta de Destino")
        self.btn_abrir_pasta.setEnabled(False)
        self.btn_abrir_pasta.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_abrir_pasta.clicked.connect(self._abrir_pasta_destino)
        lay_rodape.addWidget(self.lbl_status, 1)
        lay_rodape.addWidget(self.btn_abrir_pasta)
        layout.addLayout(lay_rodape)

    def _aplicar_estilo(self) -> None:
        self.setStyleSheet(
            """
            QMainWindow, QWidget {
                background-color: #1E293B;
                color: #F1F5F9;
                font-family: 'Segoe UI', 'Cantarell', 'Ubuntu', sans-serif;
                font-size: 13px;
            }
            #AreaDrop {
                border: 2px dashed #475569;
                border-radius: 10px;
                background-color: #0F172A;
            }
            #AreaDrop:hover {
                border-color: #E11D48;
                background-color: #162033;
            }
            #BtnProcurar {
                background-color: #1E293B;
                border: 1px solid #38BDF8;
                color: #38BDF8;
                padding: 6px 16px;
            }
            #BtnProcurar:hover {
                background-color: #0284C7;
                color: #FFFFFF;
            }
            #BannerUpdate {
                background-color: #064E3B;
                border: 1px solid #10B981;
                border-radius: 6px;
                padding: 4px 8px;
            }
            QLineEdit, QComboBox, QDoubleSpinBox, QTextEdit {
                background-color: #0F172A;
                border: 1px solid #334155;
                border-radius: 6px;
                padding: 6px;
                color: #F8FAFC;
            }
            QPushButton {
                background-color: #334155;
                border: 1px solid #475569;
                border-radius: 6px;
                padding: 7px 12px;
                color: #F8FAFC;
                font-weight: 600;
            }
            QPushButton:hover {
                background-color: #475569;
            }
            QPushButton:disabled {
                background-color: #1E293B;
                color: #64748B;
                border-color: #334155;
            }
            #BtnPerfil:checked {
                background-color: #BE123C;
                border-color: #F43F5E;
            }
            #BtnExecutar {
                background-color: #E11D48;
                border: none;
                font-size: 15px;
                font-weight: bold;
            }
            #BtnExecutar:hover {
                background-color: #BE123C;
            }
            QProgressBar {
                background-color: #0F172A;
                border-radius: 4px;
            }
            QProgressBar::chunk {
                background-color: #E11D48;
                border-radius: 4px;
            }
            """
        )

    def _checar_atualizacoes(self) -> None:
        self.updater_thread = UpdaterWorker()
        self.updater_thread.atualizacao_encontrada.connect(self._mostrar_banner_update)
        self.updater_thread.start()

    def _mostrar_banner_update(self, info: Dict[str, str]) -> None:
        self.url_atualizacao = info["url_download"]
        self.lbl_update.setText(f"Nova versão disponível: Gensai v{info['versao']}!")
        self.banner_update.setVisible(True)

    def _abrir_link_atualizacao(self) -> None:
        if self.url_atualizacao:
            webbrowser.open(self.url_atualizacao)

    def _ao_selecionar_arquivo(self, caminho: str) -> None:
        self.arquivo_entrada = caminho
        if not self.input_pasta.text():
            self.ultima_pasta_saida = Path(caminho).parent
        self.lbl_status.setText("Arquivo carregado. Pronto para executar.")

    def _selecionar_pasta_saida(self) -> None:
        pasta = QFileDialog.getExistingDirectory(
            self,
            "Escolher pasta de destino",
            str(Path.home() / "Documentos"),
        )
        if pasta:
            self.input_pasta.setText(pasta)
            self.ultima_pasta_saida = Path(pasta)

    def _iniciar_processamento(self) -> None:
        if not self.arquivo_entrada:
            QMessageBox.warning(self, "Atenção", "Selecione ou arraste um arquivo PDF primeiro.")
            return

        pasta_saida = self.input_pasta.text().strip() or None
        nivel = self.combo_nivel.currentData()
        limite_mb = self.spin_limite.value()
        pdfa = 1 if self.chk_pdfa.isChecked() else 0
        cinza = self.chk_cinza.isChecked()

        self.btn_executar.setEnabled(False)
        self.btn_abrir_pasta.setEnabled(False)
        self.progresso.setRange(0, 0)  # Barra indeterminada durante processamento
        self.lbl_status.setText("Processando com Ghostscript e pikepdf... Aguarde.")
        self.txt_resultado.clear()

        self.worker = BattousaiWorker(
            entrada=self.arquivo_entrada,
            pasta_saida=pasta_saida,
            nivel=nivel,
            limite_mb=limite_mb,
            pdfa=pdfa,
            cinza=cinza,
        )
        self.worker.concluido.connect(self._ao_concluir)
        self.worker.erro.connect(self._ao_falhar)
        self.worker.start()

    def _ao_concluir(self, arquivos: List[Path], tamanho_orig_mb: float) -> None:
        self.progresso.setRange(0, 100)
        self.progresso.setValue(100)
        self.btn_executar.setEnabled(True)

        if arquivos:
            self.ultima_pasta_saida = arquivos[0].parent
            self.btn_abrir_pasta.setEnabled(True)

        tamanho_final_mb = sum(f.stat().st_size for f in arquivos) / (1024 * 1024)
        reducao = (1 - (tamanho_final_mb / tamanho_orig_mb)) * 100 if tamanho_orig_mb > 0 else 0

        linhas = [
            f"Concluído com sucesso! ({len(arquivos)} arquivo(s) gerado(s))",
            f"Original: {tamanho_orig_mb:.2f} MB  ->  Final: {tamanho_final_mb:.2f} MB ({reducao:.1f}% de redução)",
            "",
        ]
        for arq in arquivos:
            mb = arq.stat().st_size / (1024 * 1024)
            linhas.append(f"• {arq.name} ({mb:.2f} MB)")

        self.txt_resultado.setPlainText("\n".join(linhas))
        self.lbl_status.setText("Corte concluído! Logs gravados em logs/gensai.log.")

    def _ao_falhar(self, mensagem_erro: str) -> None:
        self.progresso.setRange(0, 100)
        self.progresso.setValue(0)
        self.btn_executar.setEnabled(True)
        self.lbl_status.setText("Falha durante o processamento.")
        QMessageBox.critical(self, "Erro no processamento", mensagem_erro)

    def _abrir_pasta_destino(self) -> None:
        if not self.ultima_pasta_saida or not self.ultima_pasta_saida.exists():
            return
        caminho = str(self.ultima_pasta_saida)
        sistema = platform.system()
        if sistema == "Windows":
            os.startfile(caminho)  # type: ignore[attr-defined]
        elif sistema == "Darwin":
            subprocess.Popen(["open", caminho])
        else:
            subprocess.Popen(["xdg-open", caminho])


def main() -> None:
    app = QApplication(sys.argv)
    icone = caminho_recurso("assets/gensai.ico")
    if icone.exists():
        app.setWindowIcon(QIcon(str(icone)))
    janela = JanelaGensai()
    janela.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()