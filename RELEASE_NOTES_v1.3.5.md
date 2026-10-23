# AIC 8800D80 para macOS — v1.3.5 estável

Esta versão melhora o desempenho do transporte USB do Wi‑Fi nativo sem trocar
o kext 0.0.18 já estabilizado. O uso normal continua exclusivamente pela
interface `en2`, pelo menu Wi‑Fi e pelo CoreWLAN do macOS; o app/UTUN legado
permanece instalado somente como caminho de recuperação.

## Resultado validado

- Pico medido neste Hackintosh: **220,41 Mbps de download** e **34,19 Mbps de
  upload** no Ookla Speedtest.
- Validação pública final da versão: **163,74 Mbps de download**, **29,03 Mbps
  de upload** e ping ocioso de **73 ms**.
- Resultado público: <https://www.speedtest.net/result/19824401216>
- Recepção confirmada em **Wi‑Fi 6 (HE SU), canal de 80 MHz**.
- Durante a validação: zero registros USB malformados, zero descarte da fila RX
  e zero erro nas transmissões USB assíncronas.
- Reconexão, reinicialização e funcionamento real foram validados na máquina de
  destino.

Os números descrevem esta máquina e esta rede; não são garantia para outros
ambientes. Sinal, interferência, canal, roteador, porta USB e servidor de teste
continuam influenciando o resultado.

## Melhorias de desempenho

- Transmissão de dados por requisições USB assíncronas, com conjunto limitado a
  **200 operações simultâneas**, equivalente ao pool não agregado do driver de
  referência.
- EAPOL e comandos que exigem confirmação permanecem no caminho síncrono para
  preservar a associação e a segurança WPA2.
- O transporte copia cada requisição antes de submetê-la, mantém o buffer vivo
  até o callback e aguarda ou aborta operações pendentes durante o fechamento.
- Recepção ampliada de 8 para **16 leitores USB simultâneos**.
- Fila RX ampliada de 2.048 para **4.096 registros**, ainda limitada para evitar
  crescimento de memória sem controle.
- O run loop agora drena as conclusões USB já disponíveis em cada ciclo,
  reduzindo pausas entre callbacks durante rajadas.
- Até 256 registros USB são drenados por ciclo e até 16 frames Ethernet são
  entregues por chamada entre o serviço e o kext.
- Telemetria de taxa RX/TX, bytes Ethernet, requisições submetidas/concluídas,
  operações simultâneas, erros, largura PHY e ocupação da fila foi adicionada
  ao log do serviço.

A agregação USB opcional do driver de referência foi implementada e testada,
mas o firmware deste dongle não confirmou os frames agregados. Ela permanece
**desativada** na versão publicada; o modo estável usa somente as escritas
assíncronas individuais validadas.

## Estabilidade e kernel panic

- Mantém o driver nativo **AICNativeProbe 0.0.18**, validado após reinício.
- Não inclui mudanças novas no kext nem na ABI kernel/serviço.
- Preserva a correção do panic da versão 0.0.17: descritores de memória são
  preparados antes de `readBytes`/`writeBytes` e concluídos em todos os
  caminhos, inclusive cópias incompletas.
- Atualização transacional da EFI, verificação de hashes e cópia de recuperação
  permanecem obrigatórias antes de qualquer alteração.

## Instalador completo

O arquivo `AIC-8800D80-Native-1.3.5.pkg` inclui:

- driver nativo AICNativeProbe 0.0.18;
- firmware e carregador USB do AIC 8800D80;
- serviço Wi‑Fi e biblioteca de transporte compilada para `x86_64`;
- integração com a interface Wi‑Fi nativa do macOS;
- scripts de instalação/atualização transacional da EFI;
- aplicativo e comando `Voltar ao AIC.command` para recuperação.

Instalações nativas 0.0.15, 0.0.16 ou 0.0.17 podem ser atualizadas depois da
validação dos hashes. Quando o kext 0.0.18 já está instalado e íntegro, o pacote
mantém seus bytes e atualiza somente os componentes de espaço de usuário.

## Compatibilidade e limitações

- Validado neste Hackintosh Intel `x86_64`, macOS 15 Sequoia, OpenCore e dongle
  USB AIC `a69c:8d80`/`a69c:8d81`.
- Apple Silicon, Hackintosh AMD, Clover, outros dongles e macOS fora da série
  15 não são suportados por este pacote.
- Somente WPA2‑PSK/CCMP foi validado. WPA3-only e redes corporativas não são
  suportadas nesta versão.
- AirDrop, Handoff e Continuity não foram validados.
- O pacote não possui assinatura Developer ID nem notarização Apple.

## Instalação e recuperação

1. Mantenha conectado o pendrive de recuperação validado deste Hackintosh.
2. Baixe `AIC-8800D80-Native-1.3.5.pkg` e confira o SHA‑256 abaixo.
3. Abra o pacote, autorize a instalação e reinicie quando solicitado.
4. Conecte pelo menu Wi‑Fi nativo do macOS a uma rede WPA2 de 5 GHz.

Para retornar ao caminho anterior, execute `/Applications/Voltar ao
AIC.command`. Se o macOS não iniciar, use o pendrive de recuperação e restaure
o backup completo da EFI.

## Verificação da release

- **168 testes Python** do serviço, protocolo, associação, transporte e
  instalador.
- Testes C++ dos contratos kernel/serviço.
- Compilação estrita do transporte C e da biblioteca `x86_64`.
- Compilação e ligação offline do kext contra os headers do macOS 15, com 895
  símbolos externos conferidos nas coleções locais.
- Payload, scripts, metadados e BOM do instalador inspecionados antes da
  publicação.
- SHA‑256 do instalador:
  `087c79afaf95381199a898e653af6641fffaac143cf9c266134b36d0705f3894`.
