#!/bin/sh
# Quarantine the exact temporary no-match kext from the earlier kmutil attempt.
# Rebuild AuxKC without touching the OpenCore EFI.
set -eu

if [ "$(/usr/bin/id -u)" -ne 0 ]; then
    echo 'Execute com sudo no Terminal.' >&2
    exit 2
fi

source=/private/tmp/aic-native-compile.EMacIx/AICNativeRegistrationProbe.kext
quarantine=/Users/victor/Documents/Codex/2026-10-19/so/work/aic-native-efi-test-recovery/adhoc-bundle.hold
[ -d "$source" ] && [ ! -e "$quarantine" ] || {
    echo 'Pacote temporário ausente ou quarentena já existente; não alterar AuxKC.' >&2
    exit 1
}
identifier=$(/usr/libexec/PlistBuddy -c 'Print :CFBundleIdentifier' "$source/Contents/Info.plist")
match=$(/usr/libexec/PlistBuddy -c "Print :IOKitPersonalities:'Disabled Native Probe':IOResourceMatch" "$source/Contents/Info.plist")
[ "$identifier" = local.victor.AICNativeProbe ] &&
    [ "$match" = local.victor.AICNativeProbe.NoAutoMatch ] || {
    echo 'O pacote temporário não corresponde ao teste anterior; abortando.' >&2
    exit 1
}
before=$(/usr/bin/kmutil inspect --optional-identifier local.victor.AICNativeProbe)
printf '%s\n' "$before" | /usr/bin/grep -Fq "$source" || {
    echo 'AuxKC não aponta para o pacote esperado; abortando.' >&2
    exit 1
}
echo 'Isolando o pacote temporário sem apagá-lo...'
/bin/mv "$source" "$quarantine"
echo 'Solicitando reconstrução da coleção auxiliar sem o pacote temporário...'
if ! /usr/bin/kmutil rebuild; then
    /bin/mv "$quarantine" "$source"
    echo 'Reconstrução falhou; pacote temporário devolvido. Não reinicie.' >&2
    exit 1
fi
echo 'Estado da coleção auxiliar após reconstrução:'
/usr/bin/kmutil inspect --optional-identifier local.victor.AICNativeProbe
echo "Pacote original isolado em $quarantine"
