# Licenças de terceiros

O Real Oficial Desktop distribui ou depende dos componentes abaixo.

## FFmpeg (builds GPL do projeto BtbN)

- O instalador embarca `ffmpeg.exe`/`ffprobe.exe` de https://github.com/BtbN/FFmpeg-Builds
  (build **GPL v3**). O FFmpeg é executado como **processo separado** (mera agregação) —
  o aplicativo não linka bibliotecas do FFmpeg.
- Texto da licença: https://www.gnu.org/licenses/gpl-3.0.html
- Código-fonte correspondente: https://github.com/BtbN/FFmpeg-Builds (inclui scripts de build
  e referências exatas de fonte por release) e https://ffmpeg.org/download.html

## Fontes (SIL Open Font License 1.1)

- **Inter** — © The Inter Project Authors — https://github.com/rsms/inter
- **Montserrat** — © The Montserrat Project Authors — https://github.com/JulietaUla/Montserrat

## Modelos de IA

- **Whisper / faster-whisper** — pesos MIT (OpenAI); runtime CTranslate2 (MIT);
  repositórios `Systran/faster-whisper-*` no Hugging Face (download no primeiro uso).
- **YuNet (detecção facial)** — licença MIT — https://github.com/opencv/opencv_zoo
  (download no primeiro uso, ~230 KB).

## Principais bibliotecas

| Componente | Licença |
|---|---|
| FastAPI, Starlette, Uvicorn | MIT / BSD |
| SQLAlchemy | MIT |
| pydantic | MIT |
| anthropic (SDK) | MIT |
| yt-dlp | Unlicense |
| OpenCV (opencv-python-headless) | Apache-2.0 |
| numpy | BSD-3 |
| soundfile / libsndfile | BSD-3 / LGPL-2.1 (dinâmico) |
| Jinja2 | BSD-3 |
| Electron | MIT |
| React, TanStack Query, react-router | MIT |
| @microsoft/fetch-event-source | MIT |

A análise semântica usa a API do Claude (Anthropic) mediante chave do usuário, sujeita aos
termos comerciais da Anthropic (https://www.anthropic.com/legal/commercial-terms).
