[Português](#portugues) · [English](#english)

<a id="portugues"></a>

# AIC 8800D80 Wi‑Fi nativo para macOS

Driver e instalador completo para usar o dongle USB **AIC 8800D80** como
interface Wi‑Fi nativa do macOS 15 Sequoia em Hackintosh Intel com OpenCore.
A versão estável atual é a **v1.4.0**, com driver nativo **0.0.23**.

**[Baixar o instalador completo v1.4.0](https://github.com/ofonsecavictor/aic-8800d80-macos/releases/tag/v1.4.0)**

> **Atenção:** o instalador modifica a EFI/OpenCore usada no boot. Tenha um
> backup completo da EFI e um pendrive de recuperação funcional. O pacote foi
> validado em uma única máquina, não possui assinatura Developer ID nem
> notarização Apple e não deve ser tratado como driver universal.

## Estado validado da v1.4.0

- Interface nativa `en2`, reconhecida pelo menu Wi‑Fi e CoreWLAN do macOS.
- Operação exclusivamente nativa no uso normal; o app/UTUN anterior permanece
  instalado apenas para recuperação.
- Associação WPA2‑PSK/CCMP em 5 GHz.
- Recepção Wi‑Fi 6 (HE SU) em canal de 80 MHz.
- Reconexão e funcionamento após reinicialização validados.
- AirDrop do Hackintosh para iPhone validado com transferência real de arquivo.
- O sentido iPhone para Hackintosh ainda não funciona nesta versão.
- Máxima medida neste Hackintosh: **220,41 Mbps de download** e
  **34,19 Mbps de upload** no Ookla Speedtest.
- Validação pública final: **163,74 Mbps de download** e **29,03 Mbps de
  upload** ([resultado Ookla](https://www.speedtest.net/result/19824401216)).
- Durante os testes: zero registros USB malformados, zero descarte da fila RX
  e zero erro nas transmissões USB assíncronas.

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

- O driver 0.0.23 adiciona a interface virtual AirLink/AWDL usada pelo AirDrop.
- A criação da interface usa uma subclasse concreta e o vtable completo do ABI
  Skywalk do macOS 15, corrigindo o kernel panic observado no driver 0.0.22.
- A interface AWDL é criada somente depois que o Wi‑Fi principal termina de
  registrar; uma falha preserva a conexão normal e publica diagnóstico.
- O kext 0.0.18 corrige a causa identificada do kernel panic da versão 0.0.17
  ao preparar e finalizar corretamente os descritores de memória do IOKit.
- A associação em 5 GHz solicita explicitamente operação de 80 MHz.
- Dados de transmissão usam um conjunto limitado a 200 requisições USB
  assíncronas; EAPOL e comandos críticos continuam síncronos.
- O transporte mantém 16 leituras USB simultâneas, fila de 4.096 registros e
  processa até 256 registros por ciclo.
- Até 16 frames Ethernet são entregues por chamada entre serviço e kext.
- O run loop drena as conclusões USB disponíveis em cada ciclo, reduzindo
  pausas do escalonador em rajadas.
- A cópia de payload usa `memmove` e submissão direta de lotes validados.
- Contadores de taxa RX/TX, largura de canal, tráfego, requisições USB,
  registros malformados, ocupação e descarte de fila permitem validar a carga.
- A agregação USB opcional do driver de referência foi testada, não foi
  confirmada pelo firmware deste dongle e fica desativada. O caminho publicado
  usa as escritas assíncronas individuais validadas.
- As otimizações de velocidade não alteram o kext já estabilizado.

## Instalador completo

O arquivo `AIC-8800D80-Native-1.4.0.pkg` contém:

- driver nativo AICNativeProbe 0.0.23;
- firmware e carregador USB;
- serviço Wi‑Fi, biblioteca de transporte e integração CoreWLAN;
- instalador/atualizador transacional da EFI com validação por hashes;
- cópia de recuperação do driver anterior;
- aplicativo legado e `Voltar ao AIC.command` para reversão.

O mesmo pacote atende instalação limpa e atualização. Em uma máquina sem o
AIC, ele instala todos os componentes e configura a EFI OpenCore usada no boot.
Instalações nativas de 0.0.15 a 0.0.22 podem ser atualizadas. Se o driver 0.0.23
já estiver instalado, o pacote verifica sua integridade antes de atualizar os
componentes em espaço de usuário.

## Instalação

1. Confirme que o Hackintosh inicia pelo OpenCore e que o pendrive de
   recuperação validado está conectado.
2. Baixe `AIC-8800D80-Native-1.4.0.pkg` na página da release e confira o
   SHA‑256 publicado junto ao arquivo.
3. Abra o pacote, leia o aviso e autorize como administrador.
4. Reinicie quando solicitado.
5. Conecte pelo menu Wi‑Fi nativo do macOS a uma rede WPA2 de 5 GHz.

Não instale a versão 1.3.3/driver 0.0.17 nem a prévia 0.0.22, associadas aos
panics corrigidos nesta versão.

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
- AirDrop iPhone → Hackintosh ainda não funciona; Handoff e Continuity não
  foram validados.
- O instalador exige um pendrive USB montado e bootável com OpenCore antes de
  alterar a EFI interna. Apenas o Hackintosh alvo foi validado em hardware.
- O repositório não inclui redistribuição reproduzível de todos os firmwares e
  kexts de terceiros usados como base do pacote completo.

## Desenvolvimento e testes

```sh
PYTHONPATH=wifi:tools:installer python3 -m unittest discover -s tests
```

A release passou por 179 testes Python, testes C++ dos contratos kernel/serviço,
comparação de 502 entradas do vtable com o BootKC local, inspeção do payload do
`.pkg`, reinicialização real, teste de velocidade e envio real por AirDrop para
um iPhone.

Não envie ao repositório senhas, perfis de rede, Chaves, logs sem revisão,
backups da EFI ou dumps privados de firmware.

---

<a id="english"></a>

# AIC 8800D80 native Wi‑Fi for macOS

Complete driver and installer that exposes the USB **AIC 8800D80** as a
native Wi‑Fi interface on an Intel Hackintosh running macOS 15 Sequoia and
OpenCore. The current stable release is **v1.4.0**, with native driver
**0.0.23**.

**[Download the complete v1.4.0 installer](https://github.com/ofonsecavictor/aic-8800d80-macos/releases/tag/v1.4.0)**

> **Warning:** the installer modifies the boot EFI/OpenCore configuration.
> Keep a complete EFI backup and a working recovery USB drive. The package was
> validated on one machine, is not signed or notarized by Apple, and is not a
> universal Hackintosh driver.

## Validated v1.4.0 state

- Native `en2` interface recognized by the macOS Wi‑Fi menu and CoreWLAN.
- Native-only operation during normal use; the previous app/UTUN path remains
  installed for recovery only.
- WPA2‑PSK/CCMP association on 5 GHz.
- Wi‑Fi 6 (HE SU) reception on an 80 MHz channel.
- Reconnection and post-reboot operation validated.
- A real file transfer from the Hackintosh to an iPhone was validated over AirDrop.
- iPhone-to-Hackintosh transfers do not work yet in this release.
- Peak measured on the target Hackintosh: **220.41 Mbps download** and
  **34.19 Mbps upload** with Ookla Speedtest.
- Final public validation: **163.74 Mbps download** and **29.03 Mbps upload**
  ([Ookla result](https://www.speedtest.net/result/19824401216)).
- Zero malformed USB records, zero RX queue drops, and zero asynchronous USB
  transmit errors during the tests.

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

- Native driver 0.0.23 adds the AirLink/AWDL virtual interface used by AirDrop.
- The virtual interface uses a concrete subclass and the complete macOS 15
  Skywalk ABI vtable, fixing the kernel panic seen with native driver 0.0.22.
- AWDL creation runs only after the primary Wi‑Fi interface is registered; a
  failure preserves normal Wi‑Fi and publishes diagnostic state.
- Native kext 0.0.18 fixes the identified 0.0.17 kernel panic cause by correctly
  preparing and completing IOKit memory descriptors.
- 5 GHz association explicitly requests 80 MHz operation.
- Data transmission uses a bounded pool of up to 200 asynchronous USB
  requests; EAPOL and critical commands remain synchronous.
- Sixteen concurrent USB reads, a 4,096-record queue, and up to 256 records
  processed per cycle keep the data endpoint supplied.
- Up to 16 Ethernet frames cross the service/kext boundary per call.
- The run loop drains all available USB completions per cycle to reduce
  scheduler stalls during bursts.
- Payload copies use `memmove` and direct submission of validated batches.
- Runtime counters expose RX/TX throughput, channel width, traffic, USB
  requests, malformed records, queue occupancy, and drops.
- Optional reference-driver USB aggregation was tested but not confirmed by
  this dongle's firmware, so the released runtime keeps it disabled and uses
  the validated individual asynchronous-write path.
- Throughput work does not replace the stabilized kext.

## Complete installer

`AIC-8800D80-Native-1.4.0.pkg` includes the native 0.0.23 driver, AIC firmware
and USB loader, Wi‑Fi service and transport library, CoreWLAN integration,
transactional EFI upgrade scripts, recovery copy, and the legacy rollback path.

The same package supports a clean installation and upgrades. On a machine
without AIC components it installs the complete stack and configures the
OpenCore EFI used for boot. Native versions 0.0.15 through 0.0.22 can be
upgraded. An existing 0.0.23 installation is integrity-checked before its
user-space components are refreshed.

## Installation

1. Confirm that the Hackintosh boots through OpenCore and connect its validated
   recovery USB drive.
2. Download `AIC-8800D80-Native-1.4.0.pkg` from the release and verify the
   published SHA‑256 digest.
3. Open the package and authorize installation as an administrator.
4. Restart when requested.
5. Connect to a 5 GHz WPA2 network using the native macOS Wi‑Fi menu.

Do not install version 1.3.3/native driver 0.0.17 or preview driver 0.0.22;
their kernel panics are fixed in this release.

## Recovery, limitations, and tests

- Logs: `/Library/Logs/AIC88M80WiFi.log` and
  `/Library/Logs/AIC88M80Installer.log`.
- `/Applications/Voltar ao AIC.command` provides a hash-checked rollback path.
- WPA2‑PSK/CCMP is the validated security mode. WPA3-only and enterprise
  networks are unsupported in this release.
- iPhone-to-Hackintosh AirDrop does not work yet; Handoff and Continuity remain
  unvalidated.
- The installer requires a mounted, bootable OpenCore USB drive before editing
  the internal EFI. Hardware validation covers only the target Hackintosh.
- Validation covered 179 Python tests, C++ kernel/service contract tests, all
  502 local BootKC vtable slots, package payload inspection, a real reboot, a
  live speed test, and a real AirDrop transfer to an iPhone.

Run the logic suite with:

```sh
PYTHONPATH=wifi:tools:installer python3 -m unittest discover -s tests
```

Never commit network passwords, profiles, Keychain contents, unredacted logs,
EFI backups, or private firmware dumps.
