# TicketBOT

Aplicativo Windows em Python e Playwright para acompanhar eventos em contas
separadas, selecionar até dois ingressos e parar na página do carrinho. Login,
CAPTCHA e pagamento são sempre manuais.

## Comportamento

- Aceita acesso por Fla-ID ou público geral.
- Permite monitorar até quatro contas ao mesmo tempo em abas diferentes.
- Mantém um perfil de navegador isolado para cada nome de conta, sem misturar
  os logins.
- Prioriza setores Norte, Sul, Leste e Oeste, nessa ordem.
- Consulta novamente quando nenhum setor permitido está disponível.
- Usa intervalo mínimo de 10 segundos.
- A primeira conta que encontrar disponibilidade assume a única tentativa de
  carrinho da rodada; as outras contas param automaticamente.
- Pode avisar pelo Telegram quando inicia, detecta o evento, encontra ingressos,
  abre o carrinho, encontra erro ou é interrompido. Todas as abas usam o mesmo
  token e Chat ID, e os avisos identificam a conta.

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

1. Em cada aba, escreva um nome diferente, como `Erick` ou `Felipe`. Esse nome
   identifica e mantém separado o perfil do navegador daquela conta.
2. Informe o ID ou a URL do evento. Se deixar vazio, escolha o jogo no
   navegador depois de iniciar.
3. Se informou apenas o ID, escolha Fla-ID ou público geral.
4. Escolha uma quantidade entre 1 e 2 e um intervalo de pelo menos 10 segundos.
5. Use **+ Adicionar conta** para criar outras abas, até o limite de quatro.
6. Clique em **Iniciar todas** ou inicie somente a aba desejada.
7. Em cada janela aberta, conclua login e CAPTCHA manualmente, quando forem
   solicitados.
8. A primeira conta que encontrar um setor disponível assume a tentativa de
   carrinho. As outras param para evitar várias reservas simultâneas.
9. Quando o carrinho abrir, finalize manualmente no navegador.

## Configurar o Telegram

1. No Telegram, abra o bot oficial `@BotFather` e crie um bot com `/newbot`.
2. Copie o token fornecido e cole no campo **Token** compartilhado.
3. Abra uma conversa com o bot que você criou e envie `/start`.
4. No TicketBOT, clique em **Buscar Chat ID**.
5. Clique em **Testar**. O mesmo Telegram será usado por todas as abas.

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
