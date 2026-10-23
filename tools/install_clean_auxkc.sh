#!/bin/sh
# Replace only the auxiliary kernel collection with a previously validated,
# exact-membership candidate. No reboot; preserve the original for recovery.
set -eu

if [ "$(/usr/bin/id -u)" -ne 0 ]; then
    echo 'Execute com autenticação de administrador do macOS.' >&2
    exit 2
fi

collection=/Library/KernelCollections/AuxiliaryKernelExtensions.kc
candidate=/private/tmp/aic-auxkc-exact-uncompressed-20261019.kc
external_backup=/Volumes/1401/AIC-EFI-backup-2026-10-19.eittfztV/AuxiliaryKernelExtensions-before-AIC-cleanup.kc
saved=/Library/KernelCollections/AuxiliaryKernelExtensions.kc.aic-before-cleanup-20261019
incoming=/Library/KernelCollections/AuxiliaryKernelExtensions.kc.aic-clean-new
source=/private/tmp/aic-native-compile.EMacIx/AICNativeRegistrationProbe.kext
quarantine=/Users/victor/Documents/Codex/2026-10-19/so/work/aic-native-efi-test-recovery/adhoc-bundle.hold
original_sha=5d901d0bd01d218a5ee47617e52b73ee4be673831a0e633c93af42a15d3465eb
candidate_sha=b0d6284fb292589af00c591a048b168937b3d4ecdcb5cab2ed3cb2681ad88880
quarantined=0
saved_original=0
success=0

hash() { /usr/bin/shasum -a 256 "$1" | /usr/bin/awk '{print $1}'; }
members() {
    /usr/bin/kmutil inspect -A "$1" 2>/dev/null |
        /usr/bin/awk 'NF >= 3 && $2 ~ /^[0-9]+([.][0-9]+)*$/ {print $1, $2, $3}' |
        /usr/bin/sort
}
links() {
    /usr/bin/kmutil inspect --show-collection-metadata -A "$1" 2>/dev/null |
        /usr/bin/awk '/^Linked against (boot|system) kernel collection UUID:/ {print}'
}
cleanup() {
    if [ "$success" -eq 0 ]; then
        if [ "$saved_original" -eq 1 ]; then
            /bin/mv -f "$saved" "$collection" ||
                echo "CRÍTICO: restaure $collection de $external_backup antes de reiniciar." >&2
        fi
        if [ "$quarantined" -eq 1 ]; then
            /bin/mv "$quarantine" "$source" || true
        fi
        if [ -f "$incoming" ]; then /bin/rm -f "$incoming"; fi
    fi
}
trap cleanup EXIT

[ "$(/usr/bin/sw_vers -buildVersion)" = 24H32 ] || exit 1
[ "$(/usr/bin/uname -m)" = x86_64 ] || exit 1
[ -f "$collection" ] && [ -f "$candidate" ] && [ -f "$external_backup" ] || exit 1
[ -d "$source" ] && [ ! -e "$quarantine" ] || exit 1
[ ! -e "$saved" ] && [ ! -e "$incoming" ] || exit 1
[ "$(hash "$collection")" = "$original_sha" ] || exit 1
[ "$(hash "$external_backup")" = "$original_sha" ] || exit 1
[ "$(hash "$candidate")" = "$candidate_sha" ] || exit 1
[ "$(/usr/libexec/PlistBuddy -c 'Print :CFBundleIdentifier' "$source/Contents/Info.plist")" = local.victor.AICNativeProbe ] || exit 1
[ "$(/usr/libexec/PlistBuddy -c "Print :IOKitPersonalities:'Disabled Native Probe':IOResourceMatch" "$source/Contents/Info.plist")" = local.victor.AICNativeProbe.NoAutoMatch ] || exit 1

expected=$(members "$collection" | /usr/bin/awk '$1 != "local.victor.AICNativeProbe"')
actual=$(members "$candidate")
[ "$expected" = "$actual" ] || {
    echo 'A coleção candidata altera outros drivers; abortando.' >&2
    exit 1
}
[ "$(members "$collection" | /usr/bin/awk '$1 == "local.victor.AICNativeProbe" {n++} END {print n+0}')" = 1 ] || exit 1
[ "$(links "$collection")" = "$(links "$candidate")" ] || exit 1

echo 'Conferidos: coleção atual, cópia no pendrive, oito drivers preservados e vínculos com o kernel.'
echo 'Isolando o kext temporário e preparando a coleção limpa...'
/bin/mv "$source" "$quarantine"
quarantined=1
/bin/cp "$candidate" "$incoming"
/usr/sbin/chown root:wheel "$incoming"
/bin/chmod 744 "$incoming"
[ "$(hash "$incoming")" = "$candidate_sha" ] || exit 1
/bin/sync

echo 'Trocando a coleção auxiliar, mantendo a anterior ao lado...'
/bin/mv "$collection" "$saved"
saved_original=1
/bin/mv "$incoming" "$collection"
[ "$(hash "$collection")" = "$candidate_sha" ] || exit 1
[ "$(members "$collection")" = "$expected" ] || exit 1
[ "$(links "$collection")" = "$(links "$saved")" ] || exit 1
/bin/sync
success=1
echo 'Coleção auxiliar limpa no disco. Original preservado no pendrive e no mesmo diretório.'
echo 'Nenhum kext foi carregado e nenhum reinício foi iniciado; verificar novamente antes do boot.'
