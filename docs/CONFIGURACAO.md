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
   - Escolha **quem analisa os cortes** deste vídeo: Claude, GPT ou Análise local
     (ver seção 3 — opções sem chave configurada aparecem desabilitadas);
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

## 3. Agentes de IA (Claude e GPT)

A cada importação o app **pergunta qual agente analisa aquele vídeo**: **Claude (Anthropic)**,
**GPT (OpenAI)** ou **Análise local** (sem IA). O padrão fica em **Configurações → Agente de IA
padrão**. Regras de honestidade da v1.2.0:

- Escolher Claude/GPT **sem chave configurada** é bloqueado na hora, com instrução clara (nada
  de processar "fingindo" IA);
- Se a IA escolhida falhar em TODOS os trechos, o processamento **falha com o motivo real**
  (chave inválida, sem créditos, firewall/TLS, modelo indisponível) em vez de entregar cortes
  genéricos em silêncio;
- A mensagem final de cada processamento informa em quantos trechos a IA de fato rodou
  (ex.: *"IA Claude claude-opus-5 em 4/4 trechos"*), e cada corte exibe a origem
  (IA Claude / IA GPT / análise local).

**Claude (Anthropic)** — chave em console.anthropic.com (formato `sk-ant-…`):

| Modelo | Custo aproximado* | Quando usar |
|---|---|---|
| **Claude Opus 5** (padrão) | ≈ US$ 0,30–0,60 / hora de vídeo | máxima qualidade editorial |
| Claude Sonnet 5 | ≈ US$ 0,15–0,35 / hora de vídeo | equilíbrio custo × qualidade |
| Claude Haiku 4.5 | ≈ US$ 0,05–0,10 / hora de vídeo | grandes volumes, triagem |

**GPT (OpenAI)** — chave em platform.openai.com (formato `sk-proj-…`); modelo padrão `gpt-5.1`
(campo aceita qualquer modelo da sua conta) e contingência opcional.

*Estimativa por hora de fala; inclui o cache de prompt (Claude) usado automaticamente.

O botão **Testar** de cada provedor percorre o **mesmo caminho da análise real** (streaming +
saída estruturada) — se ele passa, o processamento com IA funciona; se falha, a mensagem já
diz o motivo em português. Testar com uma chave digitada e válida também **salva a chave**.

**Análise econômica (Batches, −50%)**: exclusiva do Claude — processa em lote (ideal de
madrugada; o resultado pode demorar mais).

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
| “Testar” do provedor de IA falha | A mensagem já diz a causa (chave inválida, sem créditos, TLS/firewall, modelo indisponível) — o teste usa o mesmo caminho da análise real |
| Processamento falhou com “A análise com … falhou em todos os trechos” | Comportamento correto da v1.2.0: a IA escolhida não funcionou e o motivo está na mensagem; corrija em Configurações (botão Testar) ou processe com “Análise local” |
| Importação por URL falha | Vídeo privado/restrito não é acessível; tente o arquivo local |
| Render falhou | Abra a Fila → mensagem de erro; espaço em disco baixo é a causa mais comum |
| Rosto errado em foco no 9:16 | No modal do corte, troque o **Enquadramento** (esquerda/direita/centro/desfocado) e atualize a prévia |
| Legenda com termo errado | Edite no modal de revisão (correção por palavra) e re-renderize |

## 11. Atualizações

Novas versões chegam como novas tags/releases. No instalador, baixe o novo
`RealOficial-Setup-*.exe` e instale por cima; no portátil, extraia o novo zip e substitua a pasta.
Dados e configurações são preservados nos dois casos — ficam em `engine-data`, fora da pasta do
app (o desinstalador também não apaga).


## 12. Novidades da v2 — Editor, Estúdio e seleção com perfis

### Editor de Corte (botão “✂ Abrir no Editor” na revisão, ou “Editor” na lista)
- **Timeline real**: miniaturas do vídeo, waveform do áudio, régua com timecode e zoom.
- **Trim** arrastando as bordas dos trechos (snap em palavra, pausa e segundo), **Dividir no
  cursor** (tecla S), **Excluir trecho** (Delete) e **restaurar** clicando na área sombreada.
- **Remover pausas**: Leve / Normal / Agressivo. Os silêncios viram jump cuts visíveis na
  timeline; pausas dramáticas (depois de “!”/“?”) são preservadas fora do Agressivo. Nada é
  aplicado até você **Salvar** — e Ctrl+Z desfaz.
- **Fades** de entrada/saída, transição nas junções, **volume/mudo/fades de áudio**.
- **Correção de palavra**: clique na palavra e digite o texto certo — vale só naquele corte;
  a transcrição original não muda.
- A edição é **não destrutiva** (EDL): o arquivo original nunca é alterado, e a MESMA edição
  alimenta a prévia e o render final (“Gerar prévia real” renderiza pelo pipeline completo).

### Estúdio de Marca (botão “Abrir Estúdio” no kit)
- Canvas 9:16 com camadas: vídeo do corte (cantos arredondados, borda, sombra), imagens/logo,
  textos com `{titulo}`, formas, vídeo decorativo (sempre mudo) e a **área das legendas**
  (define onde os cartões aparecem).
- Fundos: cor, degradê, **vídeo desfocado**, imagem ou vídeo. Animações de entrada e timing
  por camada. **Templates prontos** para começar.
- Kits antigos abrem automaticamente convertidos; só passam a usar o novo layout ao salvar.

### Enquadramento e punch-in (na revisão do corte)
- Modos: Auto (falante ativo) · Esquerda · Direita · Centro · Desfocado · **Fit (sem corte)** ·
  **Duas pessoas (empilhado)** · **Split Screen**.
- **Enquadramento por trecho** (no Editor): force o foco num intervalo — ex.: 18–24s → esquerda.
- **Punch-in**: Leve (zoom constante 105%) ou Dinâmico (alterna 110% a cada troca de segmento).

### Perfis de quantidade e reservas
- Na importação (ou em Configurações → Cortes): **Conservador** (poucos e fortes),
  **Balanceado**, **Alto volume**, **Personalizado** (score mínimo, distância mínima e teto).
- O projeto mostra o **funil da análise** (candidatos → válidos → dedup → recomendados) e, se o
  vídeo render menos cortes que a meta, o app **avisa em vez de inventar cortes ruins** — as
  sobras boas ficam em reserva no botão **“Mostrar mais oportunidades”** (sem custo de IA).


---

## 13. Novidades da v3 — o fluxo editorial e o Editor completo

A v3 separa em definitivo **avaliar** de **editar**. Nada do que você já fazia
se perdeu: o que mudou foi onde cada coisa mora.

### 13.1 Para revisar / Aprovados / Rejeitados

O projeto abre em **Para revisar** — e ali fica **só o que ainda exige uma
decisão sua**. Ao aprovar, o corte sai da lista na hora e aparece em
**Aprovados**; ao rejeitar, vai para **Rejeitados** (com um **Desfazer** por
alguns segundos). Em Rejeitados existe **Restaurar para revisão**; enquanto o
corte estiver rejeitado, ele não renderiza.

Depois de revisar vinte cortes, olhar para “Para revisar” responde na hora o
que falta.

### 13.2 A tela do corte é editorial

Clicar num corte abre uma tela para **decidir**, não para mexer no vídeo:

- player para assistir (nada de controles de edição em volta);
- **Título** e **Descrição** — a descrição é nova e já fica guardada como
  metadado de publicação para o módulo futuro de postagem;
- a análise (gancho, desenvolvimento, conclusão, pontos fortes e fracos,
  público), expansível com os 18 parâmetros;
- **Aprovar**, **Rejeitar**, **✂ Editor** e **Fechar** — e, quando aprovado,
  **Renderizar** na própria tela.

Alterar o vídeo agora só acontece dentro do Editor. Essa é a regra.

### 13.3 Estado de renderização e “Render desatualizado”

O estado editorial (para revisar / aprovado / rejeitado) e o estado técnico
(não renderizado / na fila / renderizando / renderizado / falhou) são coisas
diferentes e aparecem separados.

Se você renderizar, voltar ao Editor e mudar qualquer coisa, o sistema marca
**⚠ Render desatualizado** e oferece **Renderizar nova versão** — você nunca
vai acreditar que o arquivo antigo tem as alterações novas.

### 13.4 O novo Editor

Vídeo grande em cima, propriedades à direita, **timeline logo abaixo do
vídeo**:

- **Canvas 9:16 WYSIWYG** — enquadramento, punch-in, legendas (com estilo,
  cores, posição e ênfases) e o Kit de Marca aparecem enquanto você edita.
  Os controles de reprodução ficam dentro do próprio vídeo (Espaço = play).
- **Inspector contextual** — as 9 ferramentas (Corte, Pausas, Áudio,
  Enquadrar, Punch-in, Legenda, Palavras, Estilo, Kit) e o painel mostra
  **apenas** a selecionada. Clicar num objeto seleciona a ferramenta dele:
  um trecho abre Corte, um bloco de enquadramento abre Enquadrar, a legenda
  no vídeo abre Legenda, um cartão de legenda abre Palavras.
- **Relógio relativo** — a timeline começa sempre em `00:00`, mesmo num corte
  que veio de `06:20` do vídeo original (a origem aparece como informação).
  As margens disponíveis antes e depois continuam ali, indicadas como
  “8,0s antes” / “15,0s depois”.
- **Tracks** — além do vídeo: **Enquadramento** (blocos que você arrasta,
  redimensiona e divide), **Legendas** (cada cartão é um bloco clicável) e
  **Punch-in**. Tudo no mesmo playhead.
- **Autosave** — o header mostra “Salvando…” e “Salvo”. **Voltar** e
  **Salvar e fechar** levam de volta ao MESMO corte, com tudo persistido.

### 13.5 Editor de palavras

Clique numa palavra da legenda para:

- **Substituir** (corrige “paleto” → “paletó” mantendo o tempo original);
- **Excluir** (some da legenda; a transcrição continua intacta e a palavra
  pode ser restaurada);
- **Inserir antes** / **Inserir depois** — a palavra nova fica **ancorada** na
  vizinha: se houver uma pausa, ela ocupa a pausa; se não houver, divide só a
  janela da âncora. As outras palavras **não** saem do lugar.

Durante a reprodução, a palavra que está sendo falada fica destacada.

### 13.6 Ênfase por palavra

Selecione uma palavra e escolha **✨ Ênfase**: Pop, Punch, Impact, **Fatality**,
Color Hit, Shake, Highlight Box, Soft Lift, Glow, Outline Burst, Flash e
Bounce — com intensidade **Suave / Normal / Forte** e cor própria.

A ênfase dispara no instante em que a palavra é falada e **nunca desloca a
linha de leitura**: a palavra cresce, o resto do cartão fica onde estava.

### 13.7 Família Palavra Pop e seletor visual

O **Palavra Pop Classic** continua exatamente como era. Ao lado dele nasceram
**Clean**, **Bold**, **Impact**, **Box**, **Neon**, **Soft** e **Minimal** —
cada um com diferença visível de verdade (tamanho, peso, caixa, brilho,
movimento). A escolha agora é por **cards de amostra**, não por lista de nomes.

### 13.8 Posição livre e cores

Arraste a legenda direto no vídeo, ou use **Posição X/Y**, **Largura máxima** e
**Alinhamento** (com atalhos Topo/Centro/Inferior). A posição é proporcional:
o que você vê na prévia é o que sai no MP4 1080×1920. Há ainda a **área
segura** opcional, que marca onde as plataformas costumam cobrir a tela.

As cinco cores (principal, palavra ativa, contorno, fundo e sombra) podem ser
ajustadas por corte, com **Restaurar padrão**. A precedência é explícita:

```
palavra (ênfase) › corte › Kit de Marca › preset
```
