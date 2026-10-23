#!/bin/sh
# Revert only the native Wi-Fi addition. Keep the AIC app and saved networks.
set -eu
/usr/bin/osascript -e 'do shell script "/usr/bin/python3 '\''/Library/Application Support/AIC88M80Driver/NativeMode/native_release.py'\'' --rollback" with administrator privileges'
printf '\nAIC selecionado. Reinicie o Mac para descarregar o driver nativo.\n'
printf 'Pressione Enter para fechar esta janela.\n'
read -r _
