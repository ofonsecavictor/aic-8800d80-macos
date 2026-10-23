# AIC 8800D80 para macOS — v1.3.4 estável

Esta release transforma o protótipo em um instalador completo de Wi‑Fi nativo
para o AIC 8800D80 neste Hackintosh Intel com macOS 15 Sequoia. A conexão usa
a interface Wi‑Fi do macOS (`en2`) e o CoreWLAN; o aplicativo AIC/UTUN não é
usado no funcionamento normal e permanece instalado somente como caminho de
recuperação.

## Resultado validado

- Download máximo medido no Ookla Speedtest: **190,24 Mbps**.
- Upload medido no mesmo teste: **29,35 Mbps**.
- Recepção confirmada em **Wi‑Fi 6 (HE SU), canal de 80 MHz**.
- Zero registros USB malformados e zero descarte da fila durante os testes.
- Reconexão, boot e uso real foram validados no computador de destino.

Esses números descrevem o teste desta máquina e não são uma garantia de
velocidade em outros ambientes. Sinal, canal, interferência, roteador, porta
USB e servidor de teste continuam influenciando o resultado.

## Estabilidade e correção do kernel panic

- Mantém o kext nativo **0.0.18**, já validado após reinicialização.
- Corrige a causa identificada do panic da versão 0.0.17: descritores de memória
  são preparados antes de `readBytes`/`writeBytes` e concluídos em todos os
  caminhos, inclusive cópias incompletas.
- Mantém o kext congelado durante os ajustes de velocidade; as otimizações
  posteriores ficam no serviço em espaço de usuário e no pedido de associação.
- Inclui atualização transacional, conferência de hashes e cópia de recuperação
  do driver anterior antes de alterar a EFI.

## Melhorias de velocidade

- Solicita explicitamente operação VHT/HE em **80 MHz** ao associar em 5 GHz.
- Mantém suporte HE MCS 0–11 para um fluxo espacial, conforme o hardware.
- Usa oito leituras USB simultâneas para manter o endpoint de dados ocupado.
- Processa até 256 registros USB por ciclo e mantém fila de 2.048 registros para
  absorver rajadas sem descarte precoce.
- Entrega até 16 frames Ethernet por chamada entre serviço e kext.
- Elimina cópias Python byte a byte usando `memmove` e submissão direta de lotes
  já validados.
- Acrescenta telemetria de largura de canal, registros malformados, ocupação e
  descartes de fila para diagnóstico sem interferir no tráfego.

## Instalador completo

O arquivo `AIC-8800D80-Native-1.3.4.pkg` inclui:

- driver nativo AICNativeProbe 0.0.18;
- firmware e carregador USB do AIC 8800D80;
- serviço Wi‑Fi e biblioteca de transporte;
- integração com a interface Wi‑Fi nativa do macOS;
- scripts de instalação/atualização transacional da EFI;
- aplicativo e comando de reversão para retornar ao modo AIC anterior.

Instalações nativas 0.0.15, 0.0.16 ou 0.0.17 podem ser atualizadas após a
validação dos hashes. Uma instalação 0.0.18 existente tem sua integridade
verificada e recebe apenas os componentes de espaço de usuário atualizados.

## Instalação

1. Mantenha conectado o pendrive de recuperação validado deste Hackintosh.
2. Abra `AIC-8800D80-Native-1.3.4.pkg` e autorize a instalação.
3. Reinicie quando o instalador solicitar.
4. Use o menu Wi‑Fi nativo do macOS para conectar à rede WPA2 de 5 GHz.

O instalador é específico deste Hackintosh Intel, macOS 15 e dongle USB
`a69c:8d81`. Ele não possui assinatura Developer ID nem notarização Apple.
Não instale a versão 1.3.3, que continha o kext 0.0.17 associado ao panic.

## Verificação

- 164 testes automatizados do serviço, protocolo, associação e instalador.
- Testes C++ dos contratos kernel/serviço, incluindo transferência em lote.
- Pacote inspecionado com `pkgutil`, scripts e payload conferidos.
- SHA‑256 publicado junto ao arquivo da release.
