# Gensai PDF

Ferramenta livre (**GNU GPLv3**) para compressão em DPI controlado, conversão opcional para padrão PDF/A e fatiamento automático de documentos por limite de megabytes, projetada para peticionamento eletrônico (**PJe, eproc e Projudi**).

## Privacidade e Segurança (LGPD)
- **Processamento 100% local:** nenhum arquivo processual é enviado para servidores externos.
- **Arquivos temporários isolados:** criados em diretório temporário do sistema e apagados automaticamente ao término da execução.
- **Logs auditáveis e seguros:** metadados operacionais gravados apenas localmente em `logs/gensai.log`.

## Requisitos
- Python 3.12+
- **Ghostscript** instalado no sistema:
  - **Fedora:** `sudo dnf install ghostscript`
  - **Windows:** [Ghostscript Downloads](https://ghostscript.com/releases/gsdnld.html) (marcar adição ao PATH)

## Instalação e Uso (Desenvolvimento)
```bash
git clone [https://github.com/dgwelsongoncalves-netizen/gensai.git](https://github.com/dgwelsongoncalves-netizen/gensai.git)
cd gensai
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Interface gráfica
python3 interface.py

# Linha de comando (CLI)
python3 gensai.py caminho/do/arquivo.pdf -n boa -l 4.5
Perfeito — estratégia bem mais inteligente. O motor já está validado e entregando as 4 partes íntegras dentro do limite (`4.25 MB`, `4.06 MB`, `4.41 MB` e `2.53 MB`). Vamos fechar o produto completo agora (**Interface Gráfica em PySide6** + **Atualizador automático via GitHub** + **GitHub Actions com `pip-audit` e Inno Setup**) e depois fazemos o *tuning* de velocidade em cima da base pronta.

---

### 1. Instale as novas dependências no seu `.venv`

Atualize o **`requirements.txt`** na raiz do projeto (enxuto e apenas com bibliotecas modernas):

```text
pikepdf>=9.0.0
PySide6>=6.7.0
requests>=2.32.0

```

No terminal do VS Code (com o `.venv` ativo), instale:

```bash
pip install -r requirements.txt

```

---

### 2. Verificador de atualizações: `src/updater.py`

Consulta a API pública de Releases do seu repositório no GitHub em segundo plano. Se o computador estiver sem internet, falha silenciosamente sem travar o programa.

```python
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

```

---

### 3. Interface Gráfica moderna: `interface.py` (na raiz do projeto)

Recursos incluídos:

* **Arrastar e soltar (*drag-and-drop*)** de arquivos PDF direto na janela;
* **Execução em `QThread`:** a janela nunca congela enquanto o Battousai processa;
* **Perfis rápidos de teto** (`1.5 MB`, `2.0 MB`, `4.5 MB`, `Sem dividir`) e escolha de pasta de destino;
* **Alerta discreto no topo** quando você publicar uma nova versão no GitHub;
* **Botão "Abrir Pasta"** compatível com Fedora (Linux) e Windows.

```python
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
from PySide6.QtGui import QDragEnterEvent, QDropEvent, QIcon
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
    """Área interativa para arrastar e soltar ou clicar para selecionar um PDF."""

    arquivo_selecionado = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        self.setAcceptDrops(True)
        self.setObjectName("AreaDrop")
        self.setMinimumHeight(105)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.label_titulo = QLabel("Arraste o PDF processual aqui ou clique para selecionar")
        self.label_titulo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.label_titulo.setStyleSheet("font-size: 14px; font-weight: bold; color: #F1F5F9;")

        self.label_arquivo = QLabel("Nenhum arquivo selecionado")
        self.label_arquivo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.label_arquivo.setStyleSheet("font-size: 12px; color: #94A3B8;")

        layout.addWidget(self.label_titulo)
        layout.addWidget(self.label_arquivo)

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            caminho, _ = QFileDialog.getOpenFileName(
                self,
                "Selecionar PDF para otimizar",
                str(Path.home() / "Documentos"),
                "Documentos PDF (*.pdf *.PDF)",
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
        self.label_arquivo.setText(f"{p.name} ({tam_mb:.2f} MB)")
        self.label_arquivo.setStyleSheet("font-size: 12px; color: #38BDF8; font-weight: bold;")
        self.arquivo_selecionado.emit(str(p))


class JanelaGensai(QMainWindow):
    """Janela principal do Gensai PDF."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(f"Gensai PDF v{__version__} — Motor Battousai")
        self.setMinimumSize(640, 620)

        icone = caminho_recurso("assets/gensai.ico")
        if icone.exists():
            self.setWindowIcon(QIcon(str(icone)))

        self.arquivo_entrada: Optional[str] = None
        self.ultima_pasta_saida: Optional[Path] = None
        self.url_atualizacao: Optional[str] = None
        self.worker: Optional[BattousaiWorker] = None

        self._construir_interface()
        self._aplicar_estilo()
        self._checar_atualizacoes()

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

        # Cabeçalho
        titulo = QLabel("GENSAI PDF")
        titulo.setStyleSheet("font-size: 22px; font-weight: 800; color: #F8FAFC; letter-spacing: 1px;")
        subtitulo = QLabel(
            "Compressão local em DPI controlado e fatiamento seguro para PJe, eproc e Projudi (LGPD)"
        )
        subtitulo.setStyleSheet("font-size: 12px; color: #94A3B8;")
        layout.addWidget(titulo)
        layout.addWidget(subtitulo)

        # Área de Arrastar e Soltar
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
        btn_pasta = QPushButton("Escolher...")
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
    janela = JanelaGensai()
    janela.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()

```

Para testar a janela no seu Fedora agora mesmo:

```bash
python3 interface.py

```

---

### 4. Script do Instalador Windows: `gerador_gensai.iss` (na raiz do projeto)

Cria o instalador oficial `Instalador_Final/Instalador_Gensai.exe` no padrão do seu Nash.

```iss
[Setup]
AppName=Gensai PDF
AppVersion=0.1.0
AppPublisher=Darllen Welson Gonçalves
AppPublisherURL=https://github.com/dgwelsongoncalves-netizen/gensai
DefaultDirName={autopf}\Gensai PDF
DefaultGroupName=Gensai PDF
LicenseFile=LICENSE
OutputDir=Instalador_Final
OutputBaseFilename=Instalador_Gensai
Compression=lzma2
SolidCompression=yes
WizardStyle=modern

[Languages]
Name: "brazilianportuguese"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "dist\gensai.exe"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\Gensai PDF"; Filename: "{app}\gensai.exe"
Name: "{autodesktop}\Gensai PDF"; Filename: "{app}\gensai.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\gensai.exe"; Description: "{cm:LaunchProgram,Gensai PDF}"; Flags: nowait postinstall skipifsilent

```

---

### 5. Pipeline CI/CD: `.github/workflows/release.yml`

Crie a pasta `.github/workflows/` e salve o arquivo **`release.yml`** dentro dela. Ele replica exatamente o seu fluxo do Nash (com `pip-audit`, validação de sintaxe, PyInstaller, Inno Setup, leitura automática de `__version__` e publicação na Release).

```yaml
name: Gerar Instalador Windows (Gensai)

on:
  push:
    branches: [ "main" ]
  workflow_dispatch:

permissions:
  contents: write

jobs:
  build:
    runs-on: windows-latest

    steps:
      - name: Baixar o código do repositório
        uses: actions/checkout@v4

      - name: Configurar Python 3.12
        uses: actions/setup-python@v5
        with:
          python-version: '3.12'

      - name: Instalar dependências atualizadas
        run: |
          python -m pip install --upgrade pip
          pip install pyinstaller
          pip install -r requirements.txt

      - name: Auditoria de Segurança nas Bibliotecas (Supply Chain)
        run: |
          pip install pip-audit
          pip-audit -r requirements.txt --desc on

      - name: Validar sintaxe do Python antes de compilar
        run: |
          python -m py_compile gensai.py interface.py src/battousai.py src/logger.py src/updater.py

      - name: Fabricar aplicativo Windows (OneFile)
        shell: pwsh
        run: |
          if (Test-Path "assets/gensai.ico") {
            pyinstaller --noconfirm --windowed --onefile --name "gensai" --icon="assets/gensai.ico" --add-data "assets/gensai.ico;assets" interface.py
          } else {
            pyinstaller --noconfirm --windowed --onefile --name "gensai" interface.py
          }

      - name: Extrair versão do Gensai para Tag Limpa
        id: get_version
        shell: pwsh
        run: |
          $content = Get-Content -Path "gensai.py" -Raw -Encoding UTF8
          if ($content -match '__version__\s*=\s*["\x27]([^"\x27]+)["\x27]') {
            $ver = $matches[1].Trim()
          } else {
            $ver = "0.1.0"
          }
          Write-Output "tag=v$ver" >> $env:GITHUB_OUTPUT
          Write-Output "versao=$ver" >> $env:GITHUB_OUTPUT
          Write-Host "Tag limpa gerada: v$ver"

      - name: Compilar o Instalador (Inno Setup)
        run: iscc /DMyAppVersion=${{ steps.get_version.outputs.versao }} gerador_gensai.iss

      - name: Verificar se o Instalador foi gerado
        shell: pwsh
        run: |
          if (-Not (Test-Path "Instalador_Final/Instalador_Gensai.exe")) {
            Write-Error "O Inno Setup não gerou Instalador_Final/Instalador_Gensai.exe!"
            exit 1
          }
          $item = Get-Item "Instalador_Final/Instalador_Gensai.exe"
          Write-Host "Instalador validado: $($item.FullName) ($($item.Length) bytes)"

      - name: Publicar Release e Instalador no GitHub
        uses: softprops/action-gh-release@v2
        with:
          files: Instalador_Final/Instalador_Gensai.exe
          tag_name: ${{ steps.get_version.outputs.tag }}
          name: Gensai PDF v${{ steps.get_version.outputs.versao }}
          body: "Instalador oficial Windows do Gensai PDF v${{ steps.get_version.outputs.versao }} (GNU GPLv3)."
          overwrite_files: true
          make_latest: true
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}

```

*(Dica: no `.gitignore`, adicione também `build/`, `dist/`, `*.spec` e `Instalador_Final/` para nunca subir arquivos de compilação.)*

---

### 6. Atualize o `README.md`

Para manter a documentação do GitHub alinhada com a interface gráfica e a licença GPLv3:

```markdown
# Gensai PDF

Ferramenta livre (**GNU GPLv3**) para compressão em DPI controlado, conversão opcional para padrão PDF/A e fatiamento automático de documentos por limite de megabytes, projetada para peticionamento eletrônico (**PJe, eproc e Projudi**).

## Privacidade e Segurança (LGPD)
- **Processamento 100% local:** nenhum arquivo processual é enviado para servidores externos.
- **Arquivos temporários isolados:** criados em diretório temporário do sistema e apagados automaticamente ao término da execução.
- **Logs auditáveis e seguros:** metadados operacionais gravados apenas localmente em `logs/gensai.log`.

## Requisitos
- Python 3.12+
- **Ghostscript** instalado no sistema:
  - **Fedora:** `sudo dnf install ghostscript`
  - **Windows:** [Ghostscript Downloads](https://ghostscript.com/releases/gsdnld.html) (marcar adição ao PATH)

## Instalação e Uso (Desenvolvimento)
```bash
git clone [https://github.com/dgwelsongoncalves-netizen/gensai.git](https://github.com/dgwelsongoncalves-netizen/gensai.git)
cd gensai
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Interface gráfica
python3 interface.py

# Linha de comando (CLI)
python3 gensai.py caminho/do/arquivo.pdf -n boa -l 4.5

---

Cria esses arquivos no VS Code e roda `python3 interface.py` para ver a janela do **Gensai** aberta aí no seu Fedora! Se curtir o visual, já fazemos o `git push` para ver o GitHub Actions construir o primeiro instalador Windows automaticamente.

```