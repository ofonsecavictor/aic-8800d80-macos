#!/bin/sh
# Read-only post-boot gate; prints no SSID, MAC address, or saved credential.
set -u

echo "Darwin: $(/usr/bin/uname -r)"
for class in AICNativeUSBProvider AICAirPortController AICInfraInterface AICNativeEthernetInterface; do
    if /usr/sbin/ioreg -p IOService -r -c "$class" -w0 | /usr/bin/grep -q '^[+]'; then
        echo "$class: presente"
    else
        echo "$class: ausente"
    fi
done
echo 'Portas de rede (sem SSID):'
/usr/sbin/networksetup -listallhardwareports 2>&1 |
    /usr/bin/awk '/^Hardware Port:|^Device:/'
echo 'Interfaces BSD:'
/sbin/ifconfig -l
