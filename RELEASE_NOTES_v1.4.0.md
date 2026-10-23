# AIC 8800D80 nativo 1.4.0

Esta é a primeira release estável do projeto com Wi-Fi nativo e suporte
parcial a AirDrop no Hackintosh Intel validado.

## Resultado validado

- macOS 15 Sequoia, Intel x86_64 e OpenCore;
- dongle AIC 8800D80 `a69c:8d80`/`a69c:8d81`;
- driver nativo `AICNativeProbe` 0.0.23 carregado em `en2`;
- Wi-Fi WPA2-PSK/CCMP em 5 GHz preservado após reinicialização;
- nenhuma ocorrência nova de kernel panic com o driver 0.0.23;
- transferência real de arquivo **Mac para iPhone** concluída via AirDrop;
- **iPhone para Mac ainda não funciona** nesta versão;
- pico medido de 220,41 Mbps de download e 34,19 Mbps de upload;
- resultado público final de 163,74/29,03 Mbps:
  https://www.speedtest.net/result/19824401216

## Correções e implementação

- Criação controlada da interface virtual AirLink/AWDL depois do registro da
  interface Wi-Fi principal.
- Subclasse concreta de `IO80211VirtualInterface` para o ABI real do Skywalk no
  macOS 15.
- Comparação automatizada das 502 entradas do vtable com o BootKC local.
- Correção do panic da prévia 0.0.22 em
  `IO80211VirtualInterface::terminate`, causado por vtable/base incorretos e
  estado privado não inicializado.
- Preservação do Wi-Fi normal quando a criação de AWDL falha.
- Ponte de frames de ação AWDL entre o macOS e o firmware AIC.
- Mantidas as correções de estabilidade e desempenho das releases 1.3.x,
  incluindo RX/TX em lotes, USB assíncrono limitado e associação de 80 MHz.

## Instalador completo

O arquivo `AIC-8800D80-Native-1.4.0.pkg` atende tanto instalação limpa quanto
atualização. Ele inclui:

- firmware AIC e carregador USB;
- driver nativo 0.0.23;
- serviço Wi-Fi e integração CoreWLAN;
- biblioteca de transporte USB;
- utilitários e runtime necessários;
- app legado de recuperação;
- `Voltar ao AIC.command`;
- instalação transacional na EFI OpenCore, com hashes e backup.

Antes de alterar a EFI interna, o instalador exige um pendrive USB montado e
bootável que contenha `EFI/BOOT/BOOTx64.efi` e `EFI/OC/OpenCore.efi`. O nome e o
UUID do pendrive não são fixos, permitindo instalação limpa em outra máquina
compatível.

Instalações nativas 0.0.15 a 0.0.22 são atualizadas. Uma instalação 0.0.23 já
existente é verificada antes de os componentes em espaço de usuário serem
atualizados.

## Segurança e recuperação

- O pacote modifica a EFI usada no boot e solicita reinicialização.
- A configuração anterior e o kext anterior são preservados para rollback.
- O instalador recusa EFI inesperada, alterações concorrentes e hashes
  divergentes.
- O pacote não possui assinatura Developer ID nem notarização Apple.
- Somente o Hackintosh alvo foi validado em hardware; não é um driver universal.

## Compatibilidade e limitações

- Suportado: Hackintosh Intel x86_64, macOS 15/Darwin 24, OpenCore e o dongle
  AIC 8800D80 indicado.
- Apple Silicon, Clover, outros dongles e outras versões do macOS não são
  suportados.
- WPA3-only e redes corporativas não foram validados.
- AirDrop iPhone para Mac, Handoff e Continuity permanecem pendentes.

## Verificação da release

- 179 testes Python;
- testes C++ dos contratos entre serviço e kernel;
- 502 slots do vtable conferidos com o BootKC local;
- validação offline do kext com `kmutil`;
- inspeção do payload e scripts do instalador;
- reinicialização real sem novo panic;
- teste real de Wi-Fi e AirDrop Mac para iPhone.

Confira o SHA-256 publicado nos assets antes de instalar.

`a1bb8a6b77478e5aabc8c1ba47593b6e7c620679ba3a84851bea1699f3be7c1f`
