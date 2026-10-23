#!/bin/sh
# Replace the currently staged native test with the power-cycle fix.
# The rollback and stage scripts validate the exact EFI, recovery image and
# OpenCore configuration. No reboot is performed here.
set -eu

if [ "$#" -ne 0 ] || [ "$(/usr/bin/id -u)" -ne 0 ]; then
    echo 'Execute como administrador, sem argumentos.' >&2
    exit 2
fi

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
if ! /usr/bin/kmutil showloaded --list-only 2>/dev/null |
    /usr/bin/grep -Eq 'local\.victor\.AICNativeProbe \(0\.0\.10\)'; then
    echo 'O kext 0.0.10 não está carregado; EFI não alterada.' >&2
    exit 1
fi

echo 'Restaurando somente o kext de teste anterior na EFI...'
sh "$script_dir/rollback_native_efi_test.sh"
echo 'Preparando o kext 0.0.11 com aviso de religamento para a interface...'
sh "$script_dir/stage_native_efi_test.sh" --apply
echo 'EFI 0.0.11 preparada; o Mac não será reiniciado automaticamente.'
