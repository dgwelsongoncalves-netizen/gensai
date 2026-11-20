# Gensai

Ferramenta livre (GNU GPLv3) para compressão em DPI controlado, conversão para padrão PDF/A e fatiamento automático de documentos por limite de megabytes, projetada para peticionamento eletrônico (PJe, eproc, Projudi).

O motor interno de processamento e corte (**Battousai**) utiliza os binários nativos do sistema operacional (`ghostscript`) combinados ao `pikepdf`.

## Privacidade e Segurança (LGPD)
- Processamento **100% local**: nenhum documento processual sai da máquina do usuário.
- Arquivos intermediários são manipulados em diretórios temporários isolados e apagados automaticamente ao término da execução.
- Sem bibliotecas congeladas ou binários legados embutidos.

## Instalação no Fedora
```bash
sudo dnf install ghostscript
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt