#include <assert.h>
#include <stdint.h>
#include <string.h>

#include "../native/AICWCLBeacon.h"

int main() {
    const uint8_t ssid[] = {'A', 'I', 'C'};
    const uint8_t bssid[] = {0x02, 0x11, 0x22, 0x33, 0x44, 0x55};
    const uint8_t ies[] = {0, 3, 'A', 'I', 'C', 48, 2, 1, 0};
    AICWCLBeaconInput input = {ssid, sizeof(ssid), bssid, 44, true, -55,
                               100, 0x0011, ies, sizeof(ies)};
    uint8_t output[sizeof(AICWCLBeaconMetadata) + sizeof(ies)] = {};
    size_t written = 0;
    assert(AICEncodeWCLBeacon(input, output, sizeof(output), written));
    assert(AICValidWCLBeaconPacket(output, written));
    assert(written == sizeof(output));
    AICWCLBeaconMetadata metadata = {};
    memcpy(&metadata, output, sizeof(metadata));
    assert(metadata.ieLength == sizeof(ies));
    assert(metadata.channelSpec == (0xd000 | 44));
    assert(metadata.channel == 44 && metadata.rssi == -55);
    assert(metadata.ssidLength == 3 && memcmp(metadata.ssid, ssid, 3) == 0);
    assert(memcmp(metadata.bssid, bssid, 6) == 0);
    assert(memcmp(output + sizeof(metadata), ies, sizeof(ies)) == 0);
    output[offsetof(AICWCLBeaconMetadata, channelSpec)] = 0;
    assert(!AICValidWCLBeaconPacket(output, written));
    output[offsetof(AICWCLBeaconMetadata, channelSpec)] = 44;
    assert(!AICEncodeWCLBeacon(input, output, sizeof(output) - 1, written));
    assert(written == 0);
    input.channel = 6;
    assert(!AICEncodeWCLBeacon(input, output, sizeof(output), written));
    input.channel = 44;
    input.rssi = -128;
    assert(!AICEncodeWCLBeacon(input, output, sizeof(output), written));
    input.rssi = -55;
    const uint8_t emptyBssid[6] = {};
    input.bssid = emptyBssid;
    assert(!AICEncodeWCLBeacon(input, output, sizeof(output), written));
    input.bssid = bssid;
    const uint8_t truncatedIE[] = {48, 3, 1};
    input.ies = truncatedIE;
    input.ieLength = sizeof(truncatedIE);
    assert(!AICEncodeWCLBeacon(input, output, sizeof(output), written));
    return 0;
}
