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
