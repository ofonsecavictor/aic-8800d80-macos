# AirDrop somente com o AIC 8800D80 / AirDrop using only the AIC 8800D80

## Português

**Estado:** pesquisa; nenhum suporte AirDrop foi implementado. A release v1.1.2 permanece inalterada.

No Mac de teste, o AIC enumera como `a69c:8d81`, mas não há `IO80211Interface` nem `awdl0`. O Wi-Fi atual usa um serviço próprio e uma interface de rede UTUN; isso fornece acesso à rede, não o enlace direto de que o AirDrop precisa. O [modelo de segurança da Apple](https://support.apple.com/en-ie/guide/security/sec2261183f4/web) descreve descoberta por Bluetooth LE e comunicação por Wi-Fi peer-to-peer.

O [driver Linux do AIC](https://github.com/radxa-pkg/aic8800/blob/main/src/USB/driver_fw/drivers/aic8800/aic8800_fdrv/rwnx_main.c) contém caminhos P2P. Isso sugere uma capacidade a investigar, **não prova compatibilidade com AWDL**, nem que a revisão/firmware deste dongle permita associação STA e AirDrop simultâneos. Projetos de driver Wi-Fi nativo para outros chips também relatam dificuldade com AWDL ([exemplo: OpenIntelWireless](https://github.com/OpenIntelWireless/itlwm/issues/292)).

O [NetworkingDriverKit público da Apple](https://developer.apple.com/documentation/networkingdriverkit) oferece somente interface Ethernet; a [orientação da Apple para Wi-Fi](https://developer.apple.com/documentation/driverkit/creating-a-driver-using-the-driverkit-sdk) aponta para uma extensão de kernel. Portanto, criar `en0` com DriverKit não faria o macOS tratar o AIC como AirPort nem habilitaria AirDrop. A SDK instalada não contém cabeçalhos públicos IO80211; a integração Wi-Fi nativa exige pesquisa de API privada e validação cuidadosa em uma EFI de testes.

Marcos técnicos, nesta ordem:

1. Medir, sem derrubar a conexão estável, versão, bits de capacidade e número de interfaces virtuais informados pelo firmware. A branch experimental já grava apenas esses quatro valores quando o serviço normalmente inicia; `tools/airdrop_preflight.py` os mostra quando disponíveis. Ainda será necessário medir suporte a quadros de gerenciamento/ação e alternância de canal. Separar o que o driver Linux implementa do que este firmware realmente confirma.
2. Prototipar **fora da EFI de uso diário** uma interface Wi-Fi nativa do macOS para o AIC. O código atual de `native_backend.py` referencia uma ponte nativa, mas o pacote 1.1.2 a mantém desativada e não inclui um driver IO80211/AWDL funcional.
3. Fazer a interface peer-to-peer trocar quadros reais com outro dispositivo Apple, mantendo a conexão à rede. A presença de `awdl0` é apenas um indicador intermediário, não prova AirDrop.
4. Testar descoberta, envio e recebimento de arquivos, reconexão Wi-Fi, Bluetooth e dois reinícios consecutivos antes de falar em suporte.

Use `python3 tools/airdrop_preflight.py` para verificar apenas os sinais locais de interface e enumeração USB. A saída não inclui SSID, MAC ou senha. O campo `airdrop_proven` ficará falso até existir um teste de transferência real; o script não habilita AirDrop.

**Regra de segurança:** não instalar um kext experimental na EFI principal nem desativar proteções do macOS para “forçar” AirDrop. Usar uma EFI de teste com backup e possibilidade de rollback.

## English

**Status:** research only; AirDrop support has not been implemented. Release v1.1.2 is unchanged.

On the test Mac, the AIC enumerates as `a69c:8d81`, but neither `IO80211Interface` nor `awdl0` is present. The current Wi-Fi uses a custom service and a UTUN network interface; it provides network access, not the direct link AirDrop needs. [Apple's security documentation](https://support.apple.com/en-ie/guide/security/sec2261183f4/web) describes Bluetooth LE discovery and peer-to-peer Wi-Fi communication.

The [AIC Linux driver](https://github.com/radxa-pkg/aic8800/blob/main/src/USB/driver_fw/drivers/aic8800/aic8800_fdrv/rwnx_main.c) contains P2P paths. This suggests a capability worth investigating, **not proven AWDL compatibility** or simultaneous STA/AirDrop operation on this dongle revision and firmware. Native Wi-Fi drivers for other chips have also encountered AWDL difficulties ([OpenIntelWireless example](https://github.com/OpenIntelWireless/itlwm/issues/292)).

Apple's public [NetworkingDriverKit](https://developer.apple.com/documentation/networkingdriverkit) supports Ethernet interfaces only; [Apple's Wi-Fi driver guidance](https://developer.apple.com/documentation/driverkit/creating-a-driver-using-the-driverkit-sdk) points to a kernel extension. Creating `en0` with DriverKit would therefore not make the AIC appear as an AirPort device or enable AirDrop. The installed SDK has no public IO80211 headers; native Wi-Fi integration requires private-API research and careful validation using a test EFI.

Engineering gates, in order:

1. Without interrupting the stable connection, record the firmware version, feature bits, and virtual interface count. The experimental branch now records only these four values when the service starts normally; `tools/airdrop_preflight.py` displays them when available. Management/action-frame support and channel switching still need investigation. Distinguish Linux-driver code paths from capabilities confirmed by this firmware.
2. Prototype an AIC-backed macOS native Wi-Fi interface **outside the daily-boot EFI**. The current `native_backend.py` references a native bridge, but package 1.1.2 disables it and includes no functioning IO80211/AWDL driver.
3. Exchange actual peer-to-peer frames with another Apple device while preserving infrastructure Wi-Fi. The presence of `awdl0` is only an intermediate signal, not proof of AirDrop.
4. Test discovery, file sending and receiving, Wi-Fi reconnection, Bluetooth, and two consecutive reboots before claiming support.

Run `python3 tools/airdrop_preflight.py` to check local interface and USB-enumeration signals only. Its output excludes SSIDs, MAC addresses, and passwords. `airdrop_proven` remains false until a real transfer test exists; this script does not enable AirDrop.

**Safety rule:** do not install an experimental kext into the primary EFI or disable macOS protections to “force” AirDrop. Use a test EFI with backup and rollback available.
