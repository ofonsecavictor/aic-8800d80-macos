# AIC 8800D80 para macOS — v1.4.0-airdrop.1 (prévia experimental)

Esta prévia publica o primeiro estágio da integração AWDL/AirDrop para o
driver Wi-Fi nativo do AIC 8800D80. Ela preserva a **v1.3.5** como release
estável recomendada para uso diário.

## O que foi implementado

- Criação controlada de uma interface virtual `awdl` pelo
  `AICAirPortController`.
- Aceitação exclusiva do papel AWDL usado pelo macOS 15; outros papéis P2P são
  recusados.
- Validação do endereço MAC virtual: exatamente 6 bytes, unicast e diferente
  de zero.
- Rotinas de ativação e desativação da interface virtual, com estado de link e
  notificação ao IO80211.
- Compatibilidade com a ABI real do `IO80211VirtualInterface` encontrada nas
  coleções de kernel do macOS 15.
- Diagnóstico AirDrop atualizado para reconhecer a interface nativa AIC
  Skywalk (`en2`) e separar a presença de `awdl0` da prova de uma transferência.
- Novo teste C++ da política de criação da interface virtual e regressões do
  diagnóstico em Python.

## Validação local

- **169 testes Python** concluídos com sucesso.
- Testes C++ dos contratos kernel/serviço concluídos com sucesso.
- Compilação e ligação offline do kext concluídas com sucesso.
- **898 símbolos externos** conferidos nas coleções de kernel locais.
- Estrutura e metadados dos bundles temporários validados.
- Nenhum arquivo desta prévia foi instalado na EFI ou carregado no kernel.

## Estado atual e limitações

Esta prévia **não entrega AirDrop funcional ainda**. O caminho completo exige,
no mínimo, encaminhar os quadros de ação AWDL entre IO80211 e o firmware AIC,
implementar a programação de canais/ROC e transportar os quadros de dados AWDL
nos dois sentidos. Nesta máquina, `awdl0` ainda não foi criado em tempo de
execução e nenhuma transferência AirDrop foi comprovada.

Por segurança, esta publicação contém somente o código-fonte. **Não há pacote
`.pkg` experimental**, porque o novo caminho de kernel ainda não passou por
boot real e poderia repetir o kernel panic observado em uma versão anterior.
Para uso normal, instale a release estável
[v1.3.5](https://github.com/ofonsecavictor/aic-8800d80-macos/releases/tag/v1.3.5).

## Compatibilidade pretendida

- Hackintosh Intel `x86_64` com macOS 15 Sequoia e OpenCore.
- Dongle USB AIC 8800D80 `a69c:8d80`/`a69c:8d81`.
- Wi-Fi principal exclusivamente pela interface nativa AIC; o app/UTUN não faz
  parte do caminho normal.

Apple Silicon, Hackintosh AMD, Clover, outros dongles e outras versões do
macOS não foram validados.
