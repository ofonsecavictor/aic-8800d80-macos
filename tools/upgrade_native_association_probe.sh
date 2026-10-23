#!/bin/sh
# Replace one association-only OpenCore probe with the next revision.
# The recovery image is checked before removing the previous test.
set -eu

if [ "$#" -ne 0 ] || [ "$(/usr/bin/id -u)" -ne 0 ]; then
    echo 'Execute como administrador, sem argumentos.' >&2
    exit 2
fi

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
backup=/Volumes/1401/AIC-EFI-backup-2026-10-19.eittfztV/efi-disk0s4.img
expected_sha=908d4e91305ae42d8e0929b10a1fd4e0cd9f0999e9e8bdebd0efda4f56e0f8e9
[ -f "$backup" ] && [ -f /Volumes/1401/EFI/BOOT/BOOTx64.efi ] || {
    echo 'Pendrive 1401 ou imagem de recuperação ausente; EFI intacta.' >&2
    exit 1
}
actual_sha=$(/usr/bin/shasum -a 256 "$backup" | /usr/bin/awk '{print $1}')
[ "$actual_sha" = "$expected_sha" ] || {
    echo 'Imagem de recuperação não passou na conferência; EFI intacta.' >&2
    exit 1
}

echo 'Removendo apenas a versão anterior do teste nativo...'
sh "$script_dir/rollback_native_efi_test.sh"
echo 'Preparando a versão nova para testar associação, sem tráfego de dados...'
sh "$script_dir/stage_native_efi_test.sh" --apply-registration-probe
echo 'Versão de associação preparada; reinício não iniciado.'
