# AIC 8800D80 para macOS (snapshot 1.1.2)

Código-fonte do serviço Wi-Fi, app de menu, carregador de firmware e instalador usados no projeto AIC 8800D80 para Hackintosh Intel com macOS 15 Sequoia.

Este repositório é um snapshot de desenvolvimento para preservar e revisar o código. Não é, por si só, uma compilação reproduzível do pacote `.pkg`: os firmwares, kexts de terceiros e binários gerados não estão incluídos. O instalador altera a EFI/OpenCore e só deve ser usado em uma máquina compatível, com backup e conhecimento dos riscos.

Diretórios:

- `wifi/`: serviço, protocolo, autenticação WPA2 e transporte USB.
- `menu/`: interface Swift da barra de menus.
- `firmware-loader/`: carregador e transporte USB para a etapa de inicialização.
- `installer/`: scripts, configuração do pacote e serviços `launchd`.
- `kexts/`: fontes das extensões específicas do AIC.
- `tests/`: testes de busca rápida e primeiro uso.

Teste de lógica sem dongle:

```sh
PYTHONPATH=wifi python3 -m unittest discover -s tests
```

Não subir perfis de rede, senhas, logs de uso, backups da EFI ou firmware de terceiros. O pacote instalável validado nesta máquina é mantido separadamente.
