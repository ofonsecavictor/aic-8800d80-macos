# AirDrop somente com o AIC 8800D80 / AirDrop using only the AIC 8800D80

## Português

**Estado:** pesquisa; nenhum suporte AirDrop foi implementado. A release v1.1.2 permanece inalterada.

No Mac de teste, o AIC enumera como `a69c:8d81`, mas não há `IO80211Interface` nem `awdl0`. O Wi-Fi atual usa um serviço próprio e uma interface de rede UTUN; isso fornece acesso à rede, não o enlace direto de que o AirDrop precisa. O [modelo de segurança da Apple](https://support.apple.com/en-ie/guide/security/sec2261183f4/web) descreve descoberta por Bluetooth LE e comunicação por Wi-Fi peer-to-peer.

O [driver Linux do AIC](https://github.com/radxa-pkg/aic8800/blob/main/src/USB/driver_fw/drivers/aic8800/aic8800_fdrv/rwnx_main.c) contém caminhos P2P. Isso sugere uma capacidade a investigar, **não prova compatibilidade com AWDL**, nem que a revisão/firmware deste dongle permita associação STA e AirDrop simultâneos. Projetos de driver Wi-Fi nativo para outros chips também relatam dificuldade com AWDL ([exemplo: OpenIntelWireless](https://github.com/OpenIntelWireless/itlwm/issues/292)).

**Medição no dongle de teste (19/10/2026):** `lmac_version=06090101`, `features=01e877d7`, `max_stations=32`, `max_interfaces=4`. Pela enumeração `mm_features` da [revisão do driver AIC fixada neste projeto](https://github.com/radxa-pkg/aic8800/blob/e9e43ed/src/USB/driver_fw/drivers/aic8800/aic8800_fdrv/lmac_msg.h), estão ligados `MM_FEAT_MROLE_BIT` (4), `MM_FEAT_P2P_BIT` (13) e `MM_FEAT_P2P_GO_BIT` (14); `MM_FEAT_CHNL_CTXT_BIT` (11) está desligado. Isso é uma declaração de capacidade do firmware, não um teste de criação de interface P2P, concorrência STA/P2P ou AWDL. O significado operacional desses bits para este firmware ainda precisa ser validado com tráfego real.

O [NetworkingDriverKit público da Apple](https://developer.apple.com/documentation/networkingdriverkit) oferece somente interface Ethernet; a [orientação da Apple para Wi-Fi](https://developer.apple.com/documentation/driverkit/creating-a-driver-using-the-driverkit-sdk) aponta para uma extensão de kernel. Portanto, criar `en0` com DriverKit não faria o macOS tratar o AIC como AirPort nem habilitaria AirDrop. A SDK instalada não contém cabeçalhos públicos IO80211; a integração Wi-Fi nativa exige pesquisa de API privada e validação cuidadosa em uma EFI de testes.

Marcos técnicos, nesta ordem:

1. Medir, sem derrubar a conexão estável, versão, bits de capacidade e número de interfaces virtuais informados pelo firmware. A branch experimental já grava apenas esses quatro valores quando o serviço normalmente inicia; `tools/airdrop_preflight.py` os mostra quando disponíveis. Ainda será necessário medir suporte a quadros de gerenciamento/ação e alternância de canal. Separar o que o driver Linux implementa do que este firmware realmente confirma.
2. Prototipar **fora da EFI de uso diário** uma interface Wi-Fi nativa do macOS para o AIC. O código atual de `native_backend.py` referencia uma ponte nativa, mas o pacote 1.1.2 a mantém desativada e não inclui um driver IO80211/AWDL funcional.
3. Fazer a interface peer-to-peer trocar quadros reais com outro dispositivo Apple, mantendo a conexão à rede. A presença de `awdl0` é apenas um indicador intermediário, não prova AirDrop.
4. Testar descoberta, envio e recebimento de arquivos, reconexão Wi-Fi, Bluetooth e dois reinícios consecutivos antes de falar em suporte.

Use `python3 tools/airdrop_preflight.py` para verificar apenas os sinais locais de interface e enumeração USB. A saída não inclui SSID, MAC ou senha. O campo `airdrop_proven` ficará falso até existir um teste de transferência real; o script não habilita AirDrop.

Para consultar o firmware **instalado agora**, execute `sudo sh tools/probe_firmware_identity.sh` no Terminal a partir da raiz deste repositório. Isso interrompe o Wi-Fi AIC por alguns segundos e tenta religar o serviço mesmo em caso de falha. A saída útil contém somente `lmac_version`, `features`, `max_stations` e `max_interfaces`. Não execute durante trabalho que dependa da conexão; se a reconexão falhar, reinicie o Mac com sua EFI de recuperação disponível.

**Próximo teste manual (ainda não executado):** `sudo sh tools/probe_p2p_vif.sh` cria uma interface STA e uma P2P no firmware, confere índices distintos, remove ambas e religa o serviço AIC. Interrompe a conexão durante o teste. Não transmite quadros P2P, não testa permanência em canal ou simultaneidade de tráfego e não habilita AirDrop. Execute apenas quando puder tolerar uma breve queda de rede, com a EFI de recuperação disponível; compartilhe somente os campos booleanos da saída, não logs de sistema que possam conter identificadores.

O [caminho RX do driver AIC](https://github.com/radxa-pkg/aic8800/blob/e9e43ed/src/USB/driver_fw/drivers/aic8800/aic8800_fdrv/rwnx_rx.c) separa quadros de gerenciamento dos dados Ethernet usando `flags_is_80211_mpdu` no [cabeçalho RX](https://github.com/radxa-pkg/aic8800/blob/e9e43ed/src/USB/driver_fw/drivers/aic8800/aic8800_fdrv/rwnx_rx.h). O parser offline `wifi/management.py` agora reconhece quadros de ação brutos em registros USB, mas ainda não foi ligado ao serviço ou validado com capturas reais. A transmissão não está pronta: o transporte USB atual só aceita descritores Ethernet/estações conhecidas, enquanto o [caminho Linux de TX de gerenciamento](https://github.com/radxa-pkg/aic8800/blob/e9e43ed/src/USB/driver_fw/drivers/aic8800/aic8800_fdrv/rwnx_tx.c) usa `TXU_CNTRL_MGMT` e pode endereçar uma estação desconhecida (`0xff`). Também falta implementar e validar `MM_REMAIN_ON_CHANNEL_REQ` antes de qualquer troca fora de canal.

**Regra de segurança:** não instalar um kext experimental na EFI principal nem desativar proteções do macOS para “forçar” AirDrop. Usar uma EFI de teste com backup e possibilidade de rollback.

## English

**Status:** research only; AirDrop support has not been implemented. Release v1.1.2 is unchanged.

On the test Mac, the AIC enumerates as `a69c:8d81`, but neither `IO80211Interface` nor `awdl0` is present. The current Wi-Fi uses a custom service and a UTUN network interface; it provides network access, not the direct link AirDrop needs. [Apple's security documentation](https://support.apple.com/en-ie/guide/security/sec2261183f4/web) describes Bluetooth LE discovery and peer-to-peer Wi-Fi communication.

The [AIC Linux driver](https://github.com/radxa-pkg/aic8800/blob/main/src/USB/driver_fw/drivers/aic8800/aic8800_fdrv/rwnx_main.c) contains P2P paths. This suggests a capability worth investigating, **not proven AWDL compatibility** or simultaneous STA/AirDrop operation on this dongle revision and firmware. Native Wi-Fi drivers for other chips have also encountered AWDL difficulties ([OpenIntelWireless example](https://github.com/OpenIntelWireless/itlwm/issues/292)).

**Measurement on the test dongle (2026-10-19):** `lmac_version=06090101`, `features=01e877d7`, `max_stations=32`, `max_interfaces=4`. According to `mm_features` in the [AIC driver revision pinned by this project](https://github.com/radxa-pkg/aic8800/blob/e9e43ed/src/USB/driver_fw/drivers/aic8800/aic8800_fdrv/lmac_msg.h), `MM_FEAT_MROLE_BIT` (4), `MM_FEAT_P2P_BIT` (13), and `MM_FEAT_P2P_GO_BIT` (14) are set; `MM_FEAT_CHNL_CTXT_BIT` (11) is clear. This is a firmware capability report, not a test of P2P interface creation, concurrent STA/P2P operation, or AWDL. The operational meaning of these bits for this firmware still needs validation with real traffic.

Apple's public [NetworkingDriverKit](https://developer.apple.com/documentation/networkingdriverkit) supports Ethernet interfaces only; [Apple's Wi-Fi driver guidance](https://developer.apple.com/documentation/driverkit/creating-a-driver-using-the-driverkit-sdk) points to a kernel extension. Creating `en0` with DriverKit would therefore not make the AIC appear as an AirPort device or enable AirDrop. The installed SDK has no public IO80211 headers; native Wi-Fi integration requires private-API research and careful validation using a test EFI.

Engineering gates, in order:

1. Without interrupting the stable connection, record the firmware version, feature bits, and virtual interface count. The experimental branch now records only these four values when the service starts normally; `tools/airdrop_preflight.py` displays them when available. Management/action-frame support and channel switching still need investigation. Distinguish Linux-driver code paths from capabilities confirmed by this firmware.
2. Prototype an AIC-backed macOS native Wi-Fi interface **outside the daily-boot EFI**. The current `native_backend.py` references a native bridge, but package 1.1.2 disables it and includes no functioning IO80211/AWDL driver.
3. Exchange actual peer-to-peer frames with another Apple device while preserving infrastructure Wi-Fi. The presence of `awdl0` is only an intermediate signal, not proof of AirDrop.
4. Test discovery, file sending and receiving, Wi-Fi reconnection, Bluetooth, and two consecutive reboots before claiming support.

Run `python3 tools/airdrop_preflight.py` to check local interface and USB-enumeration signals only. Its output excludes SSIDs, MAC addresses, and passwords. `airdrop_proven` remains false until a real transfer test exists; this script does not enable AirDrop.

To query the firmware **currently installed**, run `sudo sh tools/probe_firmware_identity.sh` in Terminal from this repository's root. This briefly interrupts AIC Wi-Fi and attempts to restart its service even if the query fails. The useful output contains only `lmac_version`, `features`, `max_stations`, and `max_interfaces`. Do not run it during connection-critical work; if reconnection fails, restart the Mac with your recovery EFI available.

**Next manual test (not yet run):** `sudo sh tools/probe_p2p_vif.sh` creates one STA and one P2P firmware interface, checks that their indices differ, removes both, and restarts the AIC service. It interrupts connectivity during the test. It does not transmit P2P frames, test remain-on-channel or concurrent traffic, or enable AirDrop. Run only when a brief network interruption is acceptable and the recovery EFI is available; share only the boolean output fields, not system logs that might contain identifiers.

The [AIC RX path](https://github.com/radxa-pkg/aic8800/blob/e9e43ed/src/USB/driver_fw/drivers/aic8800/aic8800_fdrv/rwnx_rx.c) separates management frames from Ethernet data using `flags_is_80211_mpdu` in the [RX header](https://github.com/radxa-pkg/aic8800/blob/e9e43ed/src/USB/driver_fw/drivers/aic8800/aic8800_fdrv/rwnx_rx.h). The offline `wifi/management.py` parser now recognizes raw action frames in USB records, but it is not wired into the service or validated against real captures. TX is not ready: the current USB transport accepts only Ethernet/known-station descriptors, while the [Linux management TX path](https://github.com/radxa-pkg/aic8800/blob/e9e43ed/src/USB/driver_fw/drivers/aic8800/aic8800_fdrv/rwnx_tx.c) uses `TXU_CNTRL_MGMT` and may address an unknown station (`0xff`). `MM_REMAIN_ON_CHANNEL_REQ` must also be implemented and validated before off-channel exchange.

**Safety rule:** do not install an experimental kext into the primary EFI or disable macOS protections to “force” AirDrop. Use a test EFI with backup and rollback available.
