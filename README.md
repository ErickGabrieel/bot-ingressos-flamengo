# TicketBOT

Aplicativo Windows em Python e Playwright para acompanhar **um evento por
execução**, selecionar até dois ingressos e parar na página do carrinho. Login,
CAPTCHA e pagamento são sempre manuais.

## Comportamento

- Aceita acesso por Fla-ID ou público geral.
- Prioriza setores Norte, Sul, Leste e Oeste, nessa ordem.
- Consulta novamente quando nenhum setor permitido está disponível.
- Usa intervalo mínimo de 30 segundos.
- Faz somente uma inclusão no carrinho por execução e encerra o monitoramento.
- Pode avisar pelo Telegram quando inicia, detecta o evento, encontra ingressos,
  abre o carrinho, encontra erro ou é interrompido.

O uso deve respeitar os termos do site e as regras aplicáveis. O aplicativo não
contorna CAPTCHA e não automatiza pagamento.

## Executar no modo de desenvolvimento

No PowerShell, dentro da pasta do projeto:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m playwright install chromium
python app.py
```

O comando antigo também continua disponível:

```powershell
python -m src.main
```

## Usar a interface

1. Informe o ID ou a URL do evento. Se deixar vazio, escolha o jogo no
   navegador depois de iniciar.
2. Se informou apenas o ID, escolha Fla-ID ou público geral.
3. Escolha uma quantidade entre 1 e 2.
4. Use um intervalo de pelo menos 30 segundos.
5. Clique em **Iniciar monitoramento**.
6. Conclua login e CAPTCHA manualmente, quando forem solicitados.
7. Quando o carrinho abrir, finalize manualmente no navegador.

## Configurar o Telegram

1. No Telegram, abra o bot oficial `@BotFather` e crie um bot com `/newbot`.
2. Copie o token fornecido e cole no campo **Token do bot**.
3. Abra uma conversa com o bot que você criou e envie `/start`.
4. No TicketBOT, clique em **Buscar Chat ID**.
5. Clique em **Testar Telegram**.

O token não é gravado pelo aplicativo e não deve ser colocado no código, em
capturas de tela ou no GitHub. Cada pessoa que receber o aplicativo deve usar o
próprio bot/token.

## Gerar o executável

O primeiro formato recomendado é uma pasta, pois facilita testes e diagnóstico:

```powershell
.\build.ps1
```

O executável será criado em:

```text
dist\TicketBOT\TicketBOT.exe
```

Para distribuir, compacte e envie a pasta inteira `dist\TicketBOT`. A pessoa não
precisará instalar Python nem VS Code.

Depois que a versão em pasta estiver validada em outro computador, também é
possível gerar um único arquivo (maior e mais lento para iniciar):

```powershell
.\build.ps1 -OneFile
```

O executável usa o Microsoft Edge instalado no Windows e tenta o Google Chrome
como alternativa. A pessoa não precisa instalar o Chromium do Playwright, mas
precisa ter Edge ou Chrome. O executável é específico para Windows.

## Desenvolvimento e testes

Execute os testes locais com:

```powershell
python -m unittest discover -v
```

Arquivos gerados em `build/`, `dist/` e `*.spec` são ignorados pelo Git.
