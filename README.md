[Português](#portugues) · [English](#english)

<a id="portugues"></a>

# AIC 8800D80 Wi‑Fi nativo para macOS

Driver e instalador experimental para usar o dongle USB **AIC 8800D80** como
interface Wi‑Fi nativa do macOS 15 Sequoia em Hackintosh Intel com OpenCore.
A versão estável atual é a **v1.3.4**, com driver nativo **0.0.18**.

**[Baixar o instalador completo v1.3.4](https://github.com/ofonsecavictor/aic-8800d80-macos/releases/tag/v1.3.4)**

> **Atenção:** o instalador modifica a EFI/OpenCore usada no boot. Tenha um
> backup completo da EFI e um pendrive de recuperação funcional. O pacote foi
> validado em uma única máquina, não possui assinatura Developer ID nem
> notarização Apple e não deve ser tratado como driver universal.

## Estado validado da v1.3.4

- Interface nativa `en2`, reconhecida pelo menu Wi‑Fi e CoreWLAN do macOS.
- Operação exclusivamente nativa no uso normal; o app/UTUN anterior permanece
  instalado apenas para recuperação.
- Associação WPA2‑PSK/CCMP em 5 GHz.
- Recepção Wi‑Fi 6 (HE SU) em canal de 80 MHz.
- Reconexão e funcionamento após reinicialização validados.
- Máxima medida neste Hackintosh: **220.41 Mbps de download** e
  **29,35 Mbps de upload** no Ookla Speedtest.
- Durante o teste: zero registros USB malformados e zero descarte da fila RX.

A velocidade não é garantida. Ela varia conforme sinal, interferência, canal,
roteador, porta USB e servidor de teste.

## Compatibilidade

| Ambiente | Estado |
| --- | --- |
| Mesmo Hackintosh Intel, macOS 15 Sequoia, OpenCore e AIC `a69c:8d81` | Validado |
| Outro Hackintosh Intel `x86_64` com macOS 15 | Experimental, não validado |
| Hackintosh AMD | Não validado |
| Apple Silicon (`arm64`) | Não suportado |
| macOS diferente do 15 / kernel diferente do 24.x | Não suportado |
| Clover, outro dongle ou outra revisão do AIC | Não suportado |

O carregador reconhece o dispositivo inicial `a69c:8d80`, carrega o firmware e
espera a reenumeração como `a69c:8d81`. Um dongle visualmente parecido pode
usar outro chip ou protocolo.

## O que mudou

- O kext 0.0.18 corrige a causa identificada do kernel panic da versão 0.0.17
  ao preparar e finalizar corretamente os descritores de memória do IOKit.
- A associação em 5 GHz solicita explicitamente operação de 80 MHz.
- O transporte mantém oito leituras USB simultâneas, fila de 2.048 registros e
  processa até 256 registros por ciclo.
- Até 16 frames Ethernet são entregues por chamada entre serviço e kext.
- A cópia de payload usa `memmove` e submissão direta de lotes validados.
- Contadores de largura de canal, registros malformados, ocupação e descarte de
  fila permitem validar a carga sem adivinhação.
- As otimizações de velocidade não alteram o kext já estabilizado.

## Instalador completo

O arquivo `AIC-8800D80-Native-1.3.4.pkg` contém:

- driver nativo AICNativeProbe 0.0.18;
- firmware e carregador USB;
- serviço Wi‑Fi, biblioteca de transporte e integração CoreWLAN;
- instalador/atualizador transacional da EFI com validação por hashes;
- cópia de recuperação do driver anterior;
- aplicativo legado e `Voltar ao AIC.command` para reversão.

Instalações nativas 0.0.15, 0.0.16 e 0.0.17 podem ser atualizadas. Se o driver
0.0.18 já estiver instalado, o pacote verifica sua integridade e atualiza os
componentes em espaço de usuário sem trocar o kext estável.

## Instalação

1. Confirme que o Hackintosh inicia pelo OpenCore e que o pendrive de
   recuperação validado está conectado.
2. Baixe `AIC-8800D80-Native-1.3.4.pkg` na página da release e confira o
   SHA‑256 publicado junto ao arquivo.
3. Abra o pacote, leia o aviso e autorize como administrador.
4. Reinicie quando solicitado.
5. Conecte pelo menu Wi‑Fi nativo do macOS a uma rede WPA2 de 5 GHz.

Não instale a versão 1.3.3/driver 0.0.17, associada ao panic corrigido nesta
versão.

## Recuperação e diagnóstico

- Logs: `/Library/Logs/AIC88M80WiFi.log` e
  `/Library/Logs/AIC88M80Installer.log`.
- Estado do serviço:
  `sudo launchctl print system/local.victor.AIC88M80WiFi`.
- O comando `/Applications/Voltar ao AIC.command` restaura o caminho anterior
  somente depois de conferir os hashes registrados.
- Se o macOS não iniciar, use o pendrive e restaure o backup completo da EFI.

Os logs podem conter SSID e informações do computador. Remova dados pessoais
antes de publicá-los.

## Limitações conhecidas

- Somente WPA2‑PSK/CCMP foi validado; WPA3‑only e redes corporativas não são
  suportadas nesta release.
- AirDrop, Handoff e Continuity não foram validados.
- O pacote é específico deste Hackintosh e exige o pendrive de recuperação
  cadastrado pelo instalador.
- O repositório não inclui redistribuição reproduzível de todos os firmwares e
  kexts de terceiros usados como base do pacote completo.

## Desenvolvimento e testes

```sh
PYTHONPATH=wifi python3 -m unittest discover -s tests
```

A release passou por 164 testes Python, testes C++ dos contratos kernel/serviço,
inspeção do payload do `.pkg`, reinicialização real e teste de velocidade.

Não envie ao repositório senhas, perfis de rede, Chaves, logs sem revisão,
backups da EFI ou dumps privados de firmware.

---

<a id="english"></a>

# AIC 8800D80 native Wi‑Fi for macOS

Experimental driver and installer that exposes the USB **AIC 8800D80** as a
native Wi‑Fi interface on an Intel Hackintosh running macOS 15 Sequoia and
OpenCore. The current stable release is **v1.3.4**, with native driver
**0.0.18**.

**[Download the complete v1.3.4 installer](https://github.com/ofonsecavictor/aic-8800d80-macos/releases/tag/v1.3.4)**

> **Warning:** the installer modifies the boot EFI/OpenCore configuration.
> Keep a complete EFI backup and a working recovery USB drive. The package was
> validated on one machine, is not signed or notarized by Apple, and is not a
> universal Hackintosh driver.

## Validated v1.3.4 state

- Native `en2` interface recognized by the macOS Wi‑Fi menu and CoreWLAN.
- Native-only operation during normal use; the previous app/UTUN path remains
  installed for recovery only.
- WPA2‑PSK/CCMP association on 5 GHz.
- Wi‑Fi 6 (HE SU) reception on an 80 MHz channel.
- Reconnection and post-reboot operation validated.
- Peak measured on the target Hackintosh: **190.24 Mbps download** and
  **29.35 Mbps upload** with Ookla Speedtest.
- Zero malformed USB records and zero RX queue drops during the test.

Performance is not guaranteed and depends on signal, interference, channel,
router, USB port, and the selected test server.

## Compatibility

| Environment | Status |
| --- | --- |
| Target Intel Hackintosh, macOS 15 Sequoia, OpenCore, AIC `a69c:8d81` | Validated |
| Another Intel `x86_64` Hackintosh on macOS 15 | Experimental, untested |
| AMD Hackintosh | Untested |
| Apple Silicon (`arm64`) | Unsupported |
| macOS other than 15 / kernel other than 24.x | Unsupported |
| Clover, another dongle, or another AIC revision | Unsupported |

The loader recognizes the initial `a69c:8d80` device, loads its firmware, and
waits for it to re-enumerate as `a69c:8d81`.

## Key changes

- Native kext 0.0.18 fixes the identified 0.0.17 kernel panic cause by correctly
  preparing and completing IOKit memory descriptors.
- 5 GHz association explicitly requests 80 MHz operation.
- Eight concurrent USB reads, a 2,048-record queue, and up to 256 records
  processed per cycle keep the data endpoint supplied.
- Up to 16 Ethernet frames cross the service/kext boundary per call.
- Payload copies use `memmove` and direct submission of validated batches.
- Runtime counters expose channel width, malformed records, queue occupancy,
  and drops.
- Throughput work does not replace the stabilized kext.

## Complete installer

`AIC-8800D80-Native-1.3.4.pkg` includes the native 0.0.18 driver, AIC firmware
and USB loader, Wi‑Fi service and transport library, CoreWLAN integration,
transactional EFI upgrade scripts, recovery copy, and the legacy rollback path.

Native 0.0.15, 0.0.16, and 0.0.17 installations can be upgraded. An existing
0.0.18 installation is integrity-checked and receives only user-space updates,
keeping the stable kext unchanged.

## Installation

1. Confirm that the Hackintosh boots through OpenCore and connect its validated
   recovery USB drive.
2. Download `AIC-8800D80-Native-1.3.4.pkg` from the release and verify the
   published SHA‑256 digest.
3. Open the package and authorize installation as an administrator.
4. Restart when requested.
5. Connect to a 5 GHz WPA2 network using the native macOS Wi‑Fi menu.

Do not install version 1.3.3/native driver 0.0.17, which contained the panic
fixed in this release.

## Recovery, limitations, and tests

- Logs: `/Library/Logs/AIC88M80WiFi.log` and
  `/Library/Logs/AIC88M80Installer.log`.
- `/Applications/Voltar ao AIC.command` provides a hash-checked rollback path.
- WPA2‑PSK/CCMP is the validated security mode. WPA3-only and enterprise
  networks are unsupported in this release.
- AirDrop, Handoff, and Continuity have not been validated.
- This package is specific to the target Hackintosh and its registered recovery
  drive.
- Validation covered 164 Python tests, C++ kernel/service contract tests,
  package payload inspection, a real reboot, and a live speed test.

Run the logic suite with:

```sh
PYTHONPATH=wifi python3 -m unittest discover -s tests
```

Never commit network passwords, profiles, Keychain contents, unredacted logs,
EFI backups, or private firmware dumps.
