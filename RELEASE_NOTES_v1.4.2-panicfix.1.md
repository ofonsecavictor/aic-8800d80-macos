# AIC 8800D80 nativo 1.4.2-panicfix.1

Prévia local para corrigir o kernel panic do driver 0.0.24. Ainda não deve ser
publicada como release nem instalada em outras máquinas antes do teste real de
boot no Hackintosh alvo.

## Causa confirmada do panic 0.0.24

Dois relatórios de panic independentes mostraram a mesma sequência:

- `IO80211VirtualInterface::postMessage`;
- `AICAirPortController::enableVirtualInterface`;
- `AICAirPortController::createAWDLInterface`;
- `AICAirPortController::awdlTimerFired`.

`postMessage` chama `IO80211SkywalkInterface::getController()` e usa o
resultado. No fallback recém-registrado, o ciclo de vida Skywalk ainda não
havia preenchido esse ponteiro, produzindo acesso nulo em `0x120`.

## Correção 0.0.25

- impede ativação enquanto `getController()` estiver nulo;
- não chama `postMessage`, altera link ou desativa pela base sem o ciclo de
  vida Skywalk pronto;
- repete a ativação por no máximo cinco tentativas;
- abandona AWDL sem derrubar o Wi-Fi principal se o controlador nunca surgir;
- protege também o recebimento de quadros de ação contra a mesma condição;
- publica propriedades de diagnóstico sobre readiness e adiamento.

## Validação local concluída

- 181 testes Python aprovados;
- testes C++ de política AWDL aprovados;
- compilação x86_64 completa;
- 1.014 símbolos externos localizados;
- 502 slots do vtable sem divergência;
- `kmutil`: kext válido, carregável e dependências OK;
- pacote completo extraído e auditado como driver 0.0.25.

## Pendente antes de publicar

- instalar apenas no Hackintosh alvo com pendrive OpenCore conectado;
- reiniciar e confirmar ausência de panic;
- confirmar Wi-Fi nativo normal;
- inspecionar readiness AWDL e presença de `awdl0`;
- testar Mac para iPhone e iPhone para Mac.

Pacote local:
`AIC-8800D80-Native-1.4.2-panicfix.1.pkg`

SHA-256:
`f8dc17823ba8f552cc5e4ff083747dbc35aaebc7b79f5c41c7fee003d9dee4a4`
