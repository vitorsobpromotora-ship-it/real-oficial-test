# Guia de Instalação e Configuração — Real Oficial Desktop

Este guia cobre do download ao primeiro corte renderizado, incluindo a configuração da IA,
censura, Brand Kit, automações pela API local e solução de problemas.

---

## 1. Instalação (Windows 10/11, 64 bits)

Cada release traz **dois formatos** — escolha um:

- **Portátil (recomendado para testar)**: `RealOficial-<versão>-x64.zip` — extraia a pasta em
  qualquer lugar (ex.: `C:\RealOficial`) e execute `Real Oficial.exe`. Não instala nada, não pede
  administrador; para "desinstalar", apague a pasta. Ideal para validar o app rodando 100% antes
  de adotar o instalador.
- **Instalador**: `RealOficial-Setup-<versão>-x64.exe` — instala por usuário, cria atalhos e
  desinstalador.

1. Baixe na página *Releases* do repositório (ou em *Actions → CI → artifacts* para builds de
   desenvolvimento: `RealOficial-Portable-x64` / `RealOficial-Setup-x64`).
2. Como o executável ainda **não é assinado digitalmente**, o Windows SmartScreen pode exibir um
   aviso azul — clique em **“Mais informações” → “Executar assim mesmo”**.
3. Abra o **Real Oficial**. Na primeira abertura, a tela "Iniciando o motor…" aparece por alguns
   segundos enquanto o serviço local sobe.

> As duas variantes usam os mesmos dados em `%APPDATA%\real-oficial\engine-data` — dá para começar
> no portátil e migrar para o instalador depois sem perder projetos nem configurações.

**Requisitos**: Windows 10/11 x64 · 8 GB de RAM (16 GB recomendado para vídeos longos) ·
~2 GB de disco para o app + espaço para seus vídeos · internet para importar por URL, baixar o
modelo de transcrição (1º uso) e usar a análise com IA.

## 2. Primeiro processamento (fluxo básico)

1. **Painel** → digite um nome (ex.: “Podcast #42”) → **Criar projeto**;
2. Dentro do projeto → **+ Importar vídeo**:
   - **Por URL**: cole o link do YouTube, Google Drive ou `.mp4` direto; ou
   - **Arquivo local**: escolha um `.mp4/.mov/.mkv/.webm`;
3. O pipeline roda sozinho: *Importando → Transcrevendo → Analisando com IA → Enquadrando*.
   Na **primeira transcrição**, o modelo Whisper é baixado (small ≈ 480 MB) — acompanhe a barra;
4. Ao terminar, a galeria mostra os **cortes ordenados por score (0–100)**, cada um com o
   **veredito editorial** (✓ postar · − revisar · ✗ descartar). Clique num corte para revisar:
   pré-visualização 9:16, **análise editorial** (gancho, ponto forte/fraco, sugestão e público,
   citando as falas reais), ajuste de início/fim (−1s/+1s), **enquadramento** (automático /
   esquerda / direita / centro / desfocado), estilo de legenda, kit de marca e o detalhamento dos
   18 parâmetros → **Aprovar** ou **Rejeitar**. Toda edição visual invalida a prévia antiga —
   clique em **Atualizar prévia** para ver o resultado;
5. Selecione os aprovados (checkbox) → **Renderizar selecionados**. Acompanhe na
   **Fila de Renderização** e use **Abrir pasta** para pegar os MP4 finais (1080×1920, prontos
   para TikTok/Reels/Shorts).

> Dica: preencha **“Sua avaliação do ranking”** (1 = melhor na sua opinião) em alguns cortes —
> isso alimenta a métrica de *qualidade do score* nos Relatórios.

## 3. Configurando a análise com IA (Claude)

Sem chave de API o app funciona em **modo local** (heurística de áudio + léxicos) — bom para testar,
mas a seleção editorial é mais fraca. Para a análise completa:

1. Crie uma chave em **console.anthropic.com** → *API Keys* (formato `sk-ant-…`) e adicione créditos;
2. No app: **Configurações → Inteligência artificial** → cole a chave → **Testar** → *Salvar*;
3. Escolha o **modelo principal**:

   | Modelo | Custo aproximado* | Quando usar |
   |---|---|---|
   | **Claude Opus 5** (padrão) | ≈ US$ 0,30–0,60 / hora de vídeo | máxima qualidade editorial |
   | Claude Sonnet 5 | ≈ US$ 0,15–0,35 / hora de vídeo | equilíbrio custo × qualidade |
   | Claude Haiku 4.5 | ≈ US$ 0,05–0,10 / hora de vídeo | grandes volumes, triagem |

   *Estimativa por hora de fala; inclui o cache de prompt que o app usa automaticamente.
4. **Modelo de contingência**: usado automaticamente se o principal falhar num trecho
   (depois dele, cai na análise local — o processamento nunca trava por causa da IA);
5. **Análise econômica (Batches, −50%)**: liga o modo em lote da API — ideal para processar
   madrugada adentro; o resultado pode demorar mais para chegar.

## 4. Transcrição e quantidade de cortes

Em **Configurações → Transcrição e cortes**:

- **Modelo Whisper**: `tiny` (rápido, menos preciso) → `small` (recomendado) → `medium`
  (mais preciso, mais lento). Trocar o modelo baixa o novo na próxima transcrição;
- **Cortes por 30 min**: padrão 15 (como a referência do produto). Vídeos densos aceitam mais;
  aulas lentas, menos.

**De onde vem a quantidade de cortes?** O número final é um funil, não um alvo fixo:
a IA propõe candidatos por trecho (~1 a cada 2 minutos de fala), depois o app remove
sobreposições (dois candidatos sobre o mesmo momento viram um) e aplica diversidade temporal,
limitado pelo alvo proporcional à duração (15 min ⇒ até ~8). A mensagem final do processamento
mostra esse funil — ex.: *"6 cortes sugeridos (alvo 8; 11 candidatos brutos, 6 após remover
sobreposições)"*. Se vierem poucos cortes, o motivo mais comum é fala esparsa/monótona no vídeo
ou análise em modo local (sem chave de API).

## 5. Censura de palavrões

**Configurações → Censura**: ligue, escolha **Beep (1 kHz)** ou **Silenciar**, e adicione termos
próprios separados por vírgula. Use `*` para cobrir flexões (ex.: `fod*` pega “foder”, “fodido”).
A comparação ignora acentos e maiúsculas, e só casa palavras inteiras (“computador” nunca é
censurado por conter “puta”). A censura é aplicada **na renderização** — cortes já aprovados podem
ser re-renderizados com a censura ativa.

## 6. Brand Kit (identidade visual)

**Kits de Marca → + Novo kit**: nome, cor do texto, cor de destaque do karaokê, fonte
(Inter/Montserrat), estilo de legenda, posição/opacidade do logo e **headline** (texto no topo —
use `{titulo}` para inserir o título do corte). Depois **Enviar logo…** (PNG/JPG/WebP, ideal com
fundo transparente). Marque **“Usar como kit padrão”** para o botão de aplicar em massa.
Na galeria: selecione vários cortes → **Aplicar kit** → **Renderizar selecionados** — é o
Bulk Editing: configure uma vez, aplique em dezenas.

## 7. Pasta de saída e dados

- **Configurações → Pasta dos vídeos renderizados**: escolha onde os MP4 finais caem
  (vazio = pasta padrão do app);
- Dados do app (banco, mídia, modelos, logs): `%APPDATA%\real-oficial\engine-data`
  (mostrado em Configurações). Logs do motor em `…\logs\engine.log`.

## 8. API local — automações (n8n, scripts, sistemas próprios)

O motor expõe uma API REST em `http://127.0.0.1:<porta>` (padrão 8756) com o **token** exibido em
**Configurações → Token da API local** (botão Copiar). Documentação interativa em `/docs`;
referência completa em `docs/API.md`.

Fluxo de automação no formato da API pública (fachada `/shorts`):

```bash
TOKEN="cole-seu-token"; BASE="http://127.0.0.1:8756"

# 1) Enviar um vídeo por URL
curl -s -X POST "$BASE/api/v1/shorts" \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"video_url": "https://www.youtube.com/watch?v=XXXX"}'
#    → {"short_job_id": "...", ...}

# 2) Acompanhar até "done" e listar clipes por score
curl -s "$BASE/api/v1/shorts/SHORT_JOB_ID" -H "Authorization: Bearer $TOKEN"

# 3) Renderizar os melhores em lote e baixar
curl -s -X POST "$BASE/api/v1/renders/batch" \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"cut_ids": ["ID1", "ID2"]}'
curl -sL "$BASE/api/v1/media/RENDER_ID/file?token=$TOKEN" -o corte.mp4
```

Eventos em tempo real (progresso de jobs/renders): `GET /api/v1/events` (SSE).

## 9. Relatórios

**Relatórios** → escolha projeto e vídeo. Você verá **taxa de aproveitamento**
(aprovados ÷ gerados), **tempo economizado** (duração + 8 min × aprovados − tempo de revisão),
**intervenção por corte**, **correlação do score da IA com o seu ranking** (Spearman), custo de IA
e tempo por estágio. Use “Abrir no navegador” para salvar/imprimir o HTML.

## 10. Solução de problemas

| Sintoma | O que fazer |
|---|---|
| “Motor indisponível” no rodapé | Feche e reabra o app; persiste? veja `engine-data\logs\engine.log` |
| SmartScreen bloqueia o instalador | “Mais informações → Executar assim mesmo” (binário sem assinatura) |
| Antivírus acusa o motor | Falso positivo comum com PyInstaller — adicione exceção para a pasta do app |
| Download do Whisper falha | Verifique a internet/proxy; o download é retomável — processe de novo |
| “Teste” da chave Anthropic falha | Confira a chave/créditos em console.anthropic.com; firewall corporativo? |
| Importação por URL falha | Vídeo privado/restrito não é acessível; tente o arquivo local |
| Render falhou | Abra a Fila → mensagem de erro; espaço em disco baixo é a causa mais comum |
| Rosto errado em foco no 9:16 | No modal do corte, troque o **Enquadramento** (esquerda/direita/centro/desfocado) e atualize a prévia |
| Legenda com termo errado | Edite no modal de revisão (correção por palavra) e re-renderize |

## 11. Atualizações

Novas versões chegam como novas tags/releases. No instalador, baixe o novo
`RealOficial-Setup-*.exe` e instale por cima; no portátil, extraia o novo zip e substitua a pasta.
Dados e configurações são preservados nos dois casos — ficam em `engine-data`, fora da pasta do
app (o desinstalador também não apaga).
