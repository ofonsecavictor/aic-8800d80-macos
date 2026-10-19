[Português](#portugues) · [English](#english)

<a id="portugues"></a>

# AIC 8800D80 Wi-Fi e Bluetooth para macOS

Projeto experimental para usar o dongle USB **AIC 8800D80** em um Hackintosh com macOS 15 Sequoia e OpenCore. A versão instalável atual é a **1.1.2**.

**[Baixar o instalador completo v1.1.2](https://github.com/ofonsecavictor/aic-8800d80-macos/releases/tag/v1.1.2)**

> **Atenção:** o instalador modifica a EFI/OpenCore usada no boot. Faça um backup próprio da **EFI inteira** e tenha um meio alternativo de inicialização antes de instalar. O pacote não tem assinatura Developer ID da Apple. Este projeto foi testado em uma máquina; não é uma garantia de funcionamento em todo Hackintosh.

## Compatibilidade

O dongle é USB: o funcionamento do rádio não depende de um modelo específico de placa-mãe. Isso **não** significa que o pacote funcione em qualquer computador, macOS ou adaptador USB.

| Ambiente | Estado na v1.1.2 |
| --- | --- |
| Hackintosh Intel `x86_64`, macOS 15 Sequoia, OpenCore, mesmo AIC 8800D80 | Testado em **uma** máquina; outras configurações ainda não foram validadas. |
| Hackintosh AMD `x86_64`, macOS 15 Sequoia, OpenCore, mesmo AIC 8800D80 | **Potencialmente compatível, não testado.** A checagem de arquitetura aceita `x86_64`, inclusive AMD; não existe uma verificação da marca da CPU. |
| Apple Silicon (`arm64`) | Não suportado: instalador e binários são `x86_64`. |
| macOS diferente do 15 Sequoia | Não suportado por este pacote; a verificação do instalador restringe a versão e os kexts são configurados para o kernel 24.x. |
| Clover, EFI OpenCore não identificável ou não gravável | O instalador interrompe sem instalar os componentes na EFI. |
| Outro dongle ou outra revisão do chip | Não presumir compatibilidade: os IDs USB, a revisão do chip e os arquivos de firmware são conferidos pelo código. |

O carregador espera o dispositivo inicial `a69c:8d80`, sua transição após carregar o firmware para `a69c:8d81` e a revisão de chip verificada no código. **“É USB” não basta:** um produto de outra marca ou revisão pode usar protocolo e firmware diferentes.

### Sobre Hackintosh AMD

Um AMD que **já inicializa o Sequoia pelo OpenCore** pode atender aos mesmos requisitos de arquitetura do pacote. O instalador preserva as entradas existentes de `Kernel/Patch`, mas altera `Kernel/Add` e NVRAM, e **substitui por versões incluídas no pacote** os kexts Lilu, BlueToolFixup, AIC88M80ModeSwitch e AICUSBTransportFixup. Por isso, uma EFI AMD já ajustada pode ter conflitos ou regressões. Os [patches de kernel para AMD](https://github.com/AMD-OSX/AMD_Vanilla) continuam sendo responsabilidade da configuração daquele Hackintosh; este pacote não os instala nem os valida.

Não publique uma conclusão de “suporte AMD” com base apenas na instalação do `.pkg`: é preciso confirmar boot, enumeração USB, Wi-Fi, Bluetooth, reconexão e novo boot na máquina AMD. Para o primeiro teste, mantenha um pendrive de boot funcional e um backup externo da EFI.

## O que está incluído

- Carregador de firmware que inicializa o AIC pelo USB e aguarda a reenumeração do dispositivo.
- Serviço Wi-Fi iniciado pelo `launchd` e app **AIC Wi-Fi** na barra de menus.
- Busca de redes ao abrir o menu, seleção de rede com indicador de conexão, armazenamento da credencial derivada no Chaves do Sistema e tentativa de reconexão automática.
- Componentes OpenCore para o dongle e integração Bluetooth: Lilu, BlueToolFixup e dois kexts específicos do AIC.
- Backup automático de `EFI/OC` antes de alterar o OpenCore. **Isso não substitui um backup próprio da EFI inteira.**

O serviço pode iniciar com o macOS sem que o menu esteja aberto; o menu é carregado na sessão do usuário. A primeira associação ainda exige escolher uma rede WPA2 e informar a senha uma vez.

## Requisitos antes de instalar

1. Hackintosh `x86_64` com **macOS 15 Sequoia** já funcional e iniciado por uma EFI OpenCore identificável.
2. Dongle **AIC 8800D80** correspondente aos IDs e à revisão acima.
3. Partição EFI de boot acessível e gravável, autorização de administrador e espaço para o backup do OpenCore.
4. `/usr/bin/python3` funcional com os módulos padrão exigidos pelo pré-instalador. Em algumas instalações do macOS isso requer as ferramentas de desenvolvimento da Apple.
5. Uma rede **WPA2-Personal/PSK com CCMP**. Redes abertas, WPA3-only e outros métodos de autenticação não são suportados nesta versão.

## Instalação e primeiro uso

1. Faça um backup da EFI inteira e confirme que consegue iniciar o computador por um pendrive ou outra EFI, caso precise reverter.
2. Baixe o `.pkg` na [Release v1.1.2](https://github.com/ofonsecavictor/aic-8800d80-macos/releases/tag/v1.1.2). Confira o SHA-256 antes de executar:

   ```text
   0c5a630029555cb22a9979a7bd6e21b072ddf1cf7e75779a39b39a5814059a20  AIC-8800D80-Complete-1.1.2.pkg
   ```

   No macOS, use `shasum -a 256 AIC-8800D80-Complete-1.1.2.pkg` para calcular o hash do arquivo baixado.
3. Abra o instalador, conceda as permissões solicitadas e leia os avisos. Ele instala o app em `/Applications/AIC Wi-Fi.app`, prepara os serviços e atualiza a EFI OpenCore de boot. O app tenta abrir na sessão atual.
4. **Reinicie** quando solicitado para ativar as alterações da EFI. Conecte o dongle, caso ainda não esteja conectado.
5. Abra o ícone AIC Wi-Fi na barra de menus. A busca começa automaticamente; escolha uma rede WPA2 e informe a senha. Aguarde a indicação de conexão sem fechar o menu.
6. Confirme acesso à rede e faça outro teste após reiniciar. O serviço tenta conectar automaticamente à rede escolhida quando o dongle e a credencial estão disponíveis.

O primeiro boot pode demorar mais por causa da inicialização USB e do carregamento de firmware. Tempo de busca, conexão e velocidade dependem do dongle, porta USB, sinal, banda e roteador; **90 Mb/s não é uma velocidade garantida**. Durante uma conexão ativa, uma busca completa pode ser adiada para não interromper o enlace USB.

## O que o instalador altera

- Copia o app para `/Applications` e os arquivos de suporte para `/Library/Application Support/AIC88M80Driver`.
- Instala serviços em `/Library/LaunchDaemons` e o menu em `/Library/LaunchAgents`.
- Identifica a partição EFI usada no boot, monta-a e copia `EFI/OC` para `/Library/Application Support/AIC88M80Driver/Backups/EFI-*/OC`.
- Copia/substitui quatro kexts em `EFI/OC/Kexts` e habilita suas entradas em `Kernel/Add` do `config.plist`.
- Adiciona `-btlfxboardid` e `-aicusbfix` aos `boot-args` e metadados Bluetooth em NVRAM no `config.plist`.

O instalador não altera intencionalmente `Kernel/Patch`, mas não analisa se todos os outros kexts, patches e opções de uma EFI específica são compatíveis com as versões incluídas. Se a etapa de atualização da EFI falhar, o código tenta restaurar as alterações dessa etapa; ainda assim, mantenha o seu próprio backup.

## Limitações conhecidas

- Apenas a combinação de hardware e macOS descrita acima recebeu teste prático. AMD ainda precisa de validação real.
- Apenas WPA2-PSK/CCMP nesta versão; não há suporte confirmado para rede aberta, WPA3-only ou autenticação corporativa.
- O projeto implementa um serviço de rede próprio; recursos do ecossistema Apple como AirDrop, Handoff e Continuity **não foram validados** por este projeto.
- **Wi‑Fi nativo ainda não funciona:** a v1.1.2 conecta pelo serviço AIC e uma interface UTUN, não por uma `IO80211Interface` do macOS. A branch de pesquisa contém um controlador IO80211 experimental que compila, mas não está instalado nem registra a interface. O foco inicial agora é fazer busca, associação e dados funcionarem nessa interface nativa; AirDrop fica para uma etapa posterior.
- A pesquisa para usar AirDrop **somente com o AIC** está em [`docs/airdrop-aic-research.md`](docs/airdrop-aic-research.md); a versão 1.1.2 ainda não oferece essa função.
- Uma busca completa é adiada quando já existe uma conexão ativa para evitar timeout do controle USB observado no dongle.
- O pacote publicado não tem assinatura Developer ID nem notarização Apple.
- O código deste repositório é um **snapshot**, não um processo de build reproduzível do `.pkg`: firmware, kexts de terceiros e binários gerados não estão versionados aqui.

## Diagnóstico e recuperação

Se não aparecer rede ou a conexão não voltar após o boot:

1. Confirme que o dongle USB correto está conectado e aparece no Relatório do Sistema → USB. Teste outra porta USB se ele não enumerar.
2. Confira se os serviços iniciaram: `sudo launchctl print system/local.victor.AIC88M80Firmware` e `sudo launchctl print system/local.victor.AIC88M80WiFi`.
3. Veja os logs locais em `/Library/Logs/AIC88M80Driver.log`, `/Library/Logs/AIC88M80WiFi.log` e `/Library/Logs/AIC88M80Installer.log`. Eles podem conter nome de rede e dados do computador; **remova informações pessoais antes de compartilhar**.
4. Confira a versão instalada com `pkgutil --pkg-info local.victor.AIC8800D80`.

Se o macOS deixar de iniciar após a instalação, use o meio alternativo de boot e **restaure seu backup da EFI**. O backup automático de `EFI/OC` fica no caminho acima, mas não é um backup completo da partição. Não substitua às cegas a EFI de outra máquina: preserve os patches AMD e demais ajustes próprios do seu hardware.

## Código-fonte

| Pasta | Conteúdo |
| --- | --- |
| [`wifi/`](wifi/) | Serviço, transporte USB, busca, autenticação WPA2, rede e relatórios. |
| [`menu/`](menu/) | App Swift da barra de menus. |
| [`firmware-loader/`](firmware-loader/) | Inicialização do firmware e comunicação USB. |
| [`installer/`](installer/) | Scripts, configuração do pacote, integração OpenCore e serviços `launchd`. |
| [`kexts/`](kexts/) | Fontes dos dois kexts específicos do AIC. |
| [`tests/`](tests/) | Testes automatizados de lógica sem dongle. |

Para executar os testes de lógica em um ambiente com Python 3:

```sh
PYTHONPATH=wifi python3 -m unittest discover -s tests
```

Não adicione ao GitHub perfis de rede, senhas, chaves, logs de uso, backups da EFI ou dumps de firmware. Para relatar um problema, inclua versão do macOS, CPU, OpenCore, IDs USB do dongle, comportamento observado e logs **revisados para remover dados pessoais**.

---

<a id="english"></a>

# AIC 8800D80 Wi-Fi and Bluetooth for macOS

An experimental project for using the **AIC 8800D80** USB dongle on a Hackintosh running macOS 15 Sequoia with OpenCore. The current installer version is **1.1.2**.

**[Download the complete v1.1.2 installer](https://github.com/ofonsecavictor/aic-8800d80-macos/releases/tag/v1.1.2)**

> **Warning:** the installer modifies the EFI/OpenCore configuration used to boot your computer. Make your own backup of the **entire EFI partition** and keep an alternative boot method available before installing. The package is not signed with an Apple Developer ID. This project has been tested on one machine; it is not guaranteed to work on every Hackintosh.

## Compatibility

The dongle uses USB, so the radio does not depend on a particular motherboard model. That **does not** mean the package works on every computer, macOS version, or USB adapter.

| Environment | Status in v1.1.2 |
| --- | --- |
| Intel `x86_64` Hackintosh, macOS 15 Sequoia, OpenCore, same AIC 8800D80 | Tested on **one** machine; other configurations have not been validated. |
| AMD `x86_64` Hackintosh, macOS 15 Sequoia, OpenCore, same AIC 8800D80 | **Potentially compatible, untested.** The architecture check accepts `x86_64`, including AMD; it does not check the CPU brand. |
| Apple Silicon (`arm64`) | Unsupported: the installer and binaries are `x86_64`. |
| macOS other than 15 Sequoia | Unsupported by this package; the installer checks the OS version and configures its kexts for kernel 24.x. |
| Clover, or an OpenCore EFI that cannot be identified or written | The installer stops without installing the EFI components. |
| A different dongle or chip revision | Do not assume compatibility: the code checks USB IDs, chip revision, and firmware files. |

The firmware loader expects the initial `a69c:8d80` USB device, its transition to `a69c:8d81` after firmware loading, and the chip revision checked in the code. **USB alone is not enough:** another product or revision may use a different protocol and firmware.

### AMD Hackintosh notes

An AMD machine that **already boots Sequoia through OpenCore** may meet the package's architecture requirements. The installer keeps existing `Kernel/Patch` entries, but changes `Kernel/Add` and NVRAM and **replaces the installed copies** of Lilu, BlueToolFixup, AIC88M80ModeSwitch, and AICUSBTransportFixup with the bundled versions. An AMD EFI that has already been tuned for its hardware may therefore encounter conflicts or regressions. That machine's [AMD kernel patches](https://github.com/AMD-OSX/AMD_Vanilla) remain its own responsibility; this package neither installs nor validates them.

Do not claim “AMD support” just because the `.pkg` installs. Boot, USB enumeration, Wi-Fi, Bluetooth, reconnection, and another reboot must all be checked on an AMD machine. Keep a working boot USB drive and an external EFI backup for the first test.

## What is included

- A firmware loader that initializes the AIC device over USB and waits for it to re-enumerate.
- A `launchd` Wi-Fi service and the **AIC Wi-Fi** menu bar app.
- Network scanning when the menu opens, network selection with a connection indicator, derived credential storage in the System Keychain, and automatic reconnection attempts.
- OpenCore components for the dongle and Bluetooth integration: Lilu, BlueToolFixup, and two AIC-specific kexts.
- An automatic backup of `EFI/OC` before OpenCore is changed. **This does not replace your own backup of the entire EFI partition.**

The service can start with macOS even when the menu app is not open; the menu app starts in the user's session. The first connection still requires selecting a WPA2 network and entering its password once.

## Requirements before installation

1. A working `x86_64` Hackintosh running **macOS 15 Sequoia**, booted through an identifiable OpenCore EFI.
2. An **AIC 8800D80** dongle matching the USB IDs and chip revision above.
3. Access to a writable boot EFI partition, administrator authorization, and enough space for the OpenCore backup.
4. A working `/usr/bin/python3` with the standard modules required by the pre-install script. On some macOS installations, this requires Apple's developer tools.
5. A **WPA2-Personal/PSK network using CCMP**. Open networks, WPA3-only networks, and other authentication methods are unsupported in this version.

## Installation and first use

1. Back up the entire EFI partition and confirm that you can boot using a USB drive or another EFI if you need to roll back.
2. Download the `.pkg` from the [v1.1.2 Release](https://github.com/ofonsecavictor/aic-8800d80-macos/releases/tag/v1.1.2). Verify its SHA-256 before running it:

   ```text
   0c5a630029555cb22a9979a7bd6e21b072ddf1cf7e75779a39b39a5814059a20  AIC-8800D80-Complete-1.1.2.pkg
   ```

   On macOS, run `shasum -a 256 AIC-8800D80-Complete-1.1.2.pkg` to calculate the downloaded file's hash.
3. Open the installer, grant the requested permissions, and read its warnings. It installs the app at `/Applications/AIC Wi-Fi.app`, prepares the services, and updates the boot OpenCore EFI. It attempts to open the app in the current session.
4. **Restart** when prompted so the EFI changes take effect. Connect the dongle if it is not already connected.
5. Open the AIC Wi-Fi menu bar icon. Scanning starts automatically; select a WPA2 network and enter its password. Wait for the connection indicator without closing the menu.
6. Verify network access and test again after another reboot. The service attempts to reconnect to the selected network when the dongle and saved credential are available.

The first boot may take longer because of USB initialization and firmware loading. Scan time, connection time, and throughput depend on the dongle, USB port, signal, band, and router; **90 Mb/s is not guaranteed**. A full scan may be deferred while connected to avoid interrupting the USB link.

## What the installer changes

- Copies the app to `/Applications` and support files to `/Library/Application Support/AIC88M80Driver`.
- Installs services in `/Library/LaunchDaemons` and the menu app in `/Library/LaunchAgents`.
- Finds and mounts the EFI partition used for boot, then copies `EFI/OC` to `/Library/Application Support/AIC88M80Driver/Backups/EFI-*/OC`.
- Copies/replaces four kexts in `EFI/OC/Kexts` and enables their entries in `Kernel/Add` in `config.plist`.
- Adds `-btlfxboardid` and `-aicusbfix` to `boot-args` and Bluetooth metadata under NVRAM in `config.plist`.

The installer does not intentionally modify `Kernel/Patch`, but it does not check whether all other kexts, patches, and settings in a particular EFI work with the bundled versions. If the EFI update step fails, the code attempts to roll back that step; you should still keep your own backup.

## Known limitations

- Practical testing covers only the hardware and macOS combination described above. AMD still needs real-world validation.
- WPA2-PSK/CCMP only in this version; open networks, WPA3-only networks, and enterprise authentication are not supported.
- The project uses its own networking service; Apple ecosystem features such as AirDrop, Handoff, and Continuity **have not been validated** by this project.
- **Native Wi‑Fi does not work yet:** v1.1.2 connects through the AIC service and a UTUN interface, not a macOS `IO80211Interface`. The research branch contains an experimental IO80211 controller that compiles but is neither installed nor registering an interface. The initial focus is native scanning, association, and data; AirDrop is deferred to a later stage.
- Research toward AirDrop **using only the AIC** is tracked in [`docs/airdrop-aic-research.md`](docs/airdrop-aic-research.md); version 1.1.2 does not provide this feature yet.
- A full scan is deferred while connected to avoid the USB control timeout observed with this dongle.
- The published package has no Apple Developer ID signature or Apple notarization.
- This repository is a source **snapshot**, not a reproducible `.pkg` build: firmware, third-party kexts, and generated binaries are not tracked here.

## Troubleshooting and recovery

If networks do not appear or the connection does not return after boot:

1. Confirm that the correct USB dongle is connected and appears in System Information → USB. Try another USB port if it does not enumerate.
2. Check that the services started: `sudo launchctl print system/local.victor.AIC88M80Firmware` and `sudo launchctl print system/local.victor.AIC88M80WiFi`.
3. Review the local logs at `/Library/Logs/AIC88M80Driver.log`, `/Library/Logs/AIC88M80WiFi.log`, and `/Library/Logs/AIC88M80Installer.log`. They may contain the network name and computer details; **remove personal information before sharing them**.
4. Check the installed version with `pkgutil --pkg-info local.victor.AIC8800D80`.

If macOS stops booting after installation, boot through your alternative method and **restore your EFI backup**. The automatic `EFI/OC` backup is stored at the path above, but it is not a backup of the whole partition. Do not blindly copy another machine's EFI: preserve AMD patches and other hardware-specific settings.

## Source code

| Directory | Contents |
| --- | --- |
| [`wifi/`](wifi/) | Service, USB transport, scanning, WPA2 authentication, networking, and reports. |
| [`menu/`](menu/) | Swift menu bar app. |
| [`firmware-loader/`](firmware-loader/) | Firmware initialization and USB communication. |
| [`installer/`](installer/) | Scripts, package settings, OpenCore integration, and `launchd` services. |
| [`kexts/`](kexts/) | Sources for the two AIC-specific kexts. |
| [`tests/`](tests/) | Automated logic tests that do not require a dongle. |

To run the logic tests in an environment with Python 3:

```sh
PYTHONPATH=wifi python3 -m unittest discover -s tests
```

Do not commit network profiles, passwords, keys, usage logs, EFI backups, or firmware dumps to GitHub. When reporting an issue, include the macOS version, CPU, OpenCore version, dongle USB IDs, observed behavior, and logs **reviewed to remove personal information**.
