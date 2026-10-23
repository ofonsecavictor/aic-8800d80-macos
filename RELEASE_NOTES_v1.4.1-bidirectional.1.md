# AIC 8800D80 nativo 1.4.1-bidirectional.1

> **RETIRADA — NÃO INSTALE.** O driver 0.0.24 causou kernel panic
> reproduzível em `IO80211VirtualInterface::postMessage` em duas
> inicializações reais. A release foi ocultada em 23 de outubro de 2026.

Esta é uma **prévia de validação** do recebimento por AirDrop no Hackintosh
Intel. Ela mantém o Wi-Fi nativo e o envio Mac para iPhone da v1.4.0 e corrige
o primeiro bloqueio confirmado no sentido iPhone para Mac: o serviço AirLink
era registrado, mas a interface AWDL permanecia desligada e sem `awdl0`.

## O que foi corrigido

- O fallback AWDL agora ativa a interface virtual somente depois de confirmar
  que ela foi criada, anexada e adotada pelo controlador.
- O driver publica `AICNativeAWDLActive`,
  `AICNativeAWDLAutoEnableAttempted` e `AICNativeAWDLAutoEnableStatus` para
  diagnóstico objetivo após o boot.
- O desligamento da interface limpa o estado ativo publicado.
- O caminho solicitado pelo próprio macOS continua com seu ciclo de vida
  original; a ativação extra é limitada ao fallback automático.
- O driver passa de 0.0.23 para **0.0.24**, permitindo atualização real do kext
  instalado em vez de somente verificar a versão anterior.

## Instalador completo

O asset `AIC-8800D80-Native-1.4.1-bidirectional.1.pkg` serve para instalação
limpa ou atualização e inclui:

- firmware AIC e carregador USB;
- driver nativo `AICNativeProbe` 0.0.24;
- serviço Wi-Fi, biblioteca de transporte e integração CoreWLAN;
- app AIC legado mantido apenas como recuperação;
- `Voltar ao AIC.command`;
- instalador e atualizador transacional da EFI OpenCore;
- backup por hash e rollback da configuração e do driver anterior.

Em uma máquina compatível sem instalação anterior, o mesmo pacote instala
todos os componentes e adiciona o kext à EFI OpenCore usada no boot. Antes de
alterar a EFI interna, ele exige um pendrive USB montado e bootável com
`EFI/BOOT/BOOTx64.efi` e `EFI/OC/OpenCore.efi`.

Instalações nativas 0.0.15 a 0.0.23 podem ser atualizadas. Uma instalação
0.0.24 existente é verificada por hashes antes de atualizar os componentes em
espaço de usuário.

## Validação realizada antes da publicação

- 180 testes Python aprovados;
- testes C++ do contrato de ativação AWDL aprovados;
- compilação x86_64 completa do kext;
- 1.014 símbolos externos encontrados nas coleções locais;
- 502 slots do vtable conferidos, sem divergências;
- `kmutil` confirmou o kext como válido, carregável e com dependências OK;
- payload final do `.pkg` extraído e auditado;
- versão 0.0.24 e marcador `0.0.24-bidirectional.1` confirmados dentro do
  asset final.

## Estado de validação e riscos

- A v1.4.0 de base foi validada sem novo kernel panic, com Wi-Fi nativo e
  AirDrop real do Mac para o iPhone.
- A correção 0.0.24 ainda precisa de reinicialização e teste real no hardware
  para confirmar `awdl0` e a transferência iPhone para Mac.
- Por isso esta publicação é marcada como **pre-release**, e a v1.4.0 continua
  sendo a release estável.
- O pacote modifica a EFI, não possui assinatura Developer ID nem notarização
  Apple e não é um driver universal.

## Compatibilidade

- Hackintosh Intel x86_64;
- macOS 15 / Darwin 24;
- OpenCore;
- AIC 8800D80 `a69c:8d80` / `a69c:8d81`.

Apple Silicon, Clover, outros dongles e outras versões do macOS não são
suportados. Handoff e Continuity continuam sem validação.

## SHA-256

`96fcfed7630c56c801577ac18ccf0ef9ca07d53cc5fbc119bcc4c2f504cb1253`
