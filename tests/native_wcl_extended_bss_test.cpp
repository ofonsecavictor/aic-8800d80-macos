#include <assert.h>
#include <stdint.h>
#include <string.h>

#include "../native/AICWCLExtendedBss.h"

int main() {
    const uint8_t ssid[] = {'A', 'I', 'C'};
    const uint8_t bssid[] = {2, 1, 2, 3, 4, 5};
    const uint8_t ies[] = {
        0, 3, 'A', 'I', 'C',
        1, 2, 0x82, 0x84,
        50, 1, 0x8b,
        48, 4, 1, 0, 2, 0,
    };
    AICWCLBeaconInput input = {ssid, sizeof(ssid), bssid, 6, false, -55,
                               100, 0x0011, ies, sizeof(ies)};
    uint8_t packet[sizeof(AICWCLBeaconMetadata) + sizeof(ies)] = {};
    uint8_t reply[kAICWCLExtendedBssSize] = {};
    size_t written = 0;
    assert(AICEncodeWCLBeacon(input, packet, sizeof(packet), written));
    assert(AICEncodeWCLExtendedBss(packet, written, reply, sizeof(reply)));
    assert(reply[0] == 1 && reply[4] == 3);
    assert(reply[8] == 1 && reply[12] == 0x82);
    assert(reply[20] == 1 && reply[24] == 0x84);
    assert(reply[32] == 1 && reply[36] == 0x8b);
    assert(reply[0xbc] == 1 && reply[0xcc] == 1 && reply[0xd4] == 1);
    assert(reply[0xd0] == 0xff && reply[0xd1] == 0xff);
    assert(reply[0xdd] == 48 && reply[0xde] == 4 && reply[0xdf] == 1);
    assert(!AICEncodeWCLExtendedBss(packet, written, reply, sizeof(reply) - 1));
    packet[0] = 255;
    assert(!AICEncodeWCLExtendedBss(packet, written, reply, sizeof(reply)));
    return 0;
}
