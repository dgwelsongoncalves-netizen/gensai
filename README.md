# Gensai PDF

Ferramenta livre (**GNU GPLv3**) para compressão em DPI controlado, conversão opcional para padrão **PDF/A** e fatiamento automático de documentos por limite de megabytes, projetada para peticionamento eletrônico (**PJe, eproc e Projudi**).

## Recursos

- **Interface Gráfica (PySide6):** suporte a arrastar e soltar (*drag-and-drop*), perfis rápidos de tamanho (1,5 MB, 2,0 MB, 4,5 MB ou sem dividir) e processamento em segundo plano sem congelar a janela.
- **Linha de Comando (CLI):** execução direta via terminal para automações e lotes.
- **Motor Battousai:** compressão com Ghostscript e fatiamento seguro com PyMuPDF (`fitz`).
- **Atualizador Integrado:** verificação silenciosa de novas versões via GitHub Releases.

## Privacidade e Segurança (LGPD)

- **Processamento 100% local:** nenhum arquivo processual é enviado para servidores externos.
- **Arquivos temporários isolados:** criados em diretório temporário do sistema e apagados automaticamente ao término da execução.
- **Logs auditáveis e seguros:** metadados operacionais gravados apenas localmente em `logs/gensai.log`.

## Requisitos

- **Python 3.12+**
- **Ghostscript** instalado no sistema:
  - **Fedora:** `sudo dnf install ghostscript`
  - **Windows:** [Ghostscript Downloads](https://ghostscript.com/releases/gsdnld.html) (marcar a opção de adicionar ao `PATH` durante a instalação)

## Instalação e Uso (Desenvolvimento)

```bash
git clone [https://github.com/dgwelsongoncalves-netizen/gensai.git](https://github.com/dgwelsongoncalves-netizen/gensai.git)
cd gensai
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

Interface Gráfica (GUI)
Bash

python3 interface.py

Linha de Comando (CLI)
Bash

python3 gensai.py caminho/do/arquivo.pdf -n boa -l 4.5

Testes Automatizados

Para executar a suíte de testes localmente (utilizando PDFs sintéticos gerados em memória e isolamento via tmp_path):
```bash
pytest
```

## Licença

Este projeto é distribuído sob a licença **GNU General Public License v3.0 (GPLv3)**. Consulte o arquivo `LICENSE` para mais detalhes.

