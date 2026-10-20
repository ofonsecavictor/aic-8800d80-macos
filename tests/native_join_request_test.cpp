#include <assert.h>
#include <stdint.h>
#include <string.h>

#include "../native/AICWCLJoinRequest.h"

static void put16(uint8_t *p, uint16_t value) {
    p[0] = uint8_t(value);
    p[1] = uint8_t(value >> 8);
}

static void put32(uint8_t *p, uint32_t value) {
    put16(p, uint16_t(value));
    put16(p + 2, uint16_t(value >> 16));
}

int main() {
    uint8_t raw[kAICWCLJoinRequestSize] = {};
    AICWCLJoinRequest result = {};
    put32(raw + 0x10, 1);
    put32(raw + 0x14, 1u << 3);
    put32(raw + 0x1c, 4);
    memcpy(raw + 0x20, "test", 4);
    put32(raw + 0x44, 32);
    put32(raw + 0x48, 6);
    memset(raw + 0x50, 0xa5, 32); // Synthetic PMK; never a real credential.
    put32(raw + 0x214, 1);
    raw[0x21c] = 2;
    raw[0x221] = 1;
    put16(raw + 0x228, 44);
    const uint8_t rsn[] = {
        48, 20, 1, 0, 0, 0x0f, 0xac, 4, 1, 0,
        0, 0x0f, 0xac, 4, 1, 0, 0, 0x0f, 0xac, 2, 0, 0
    };
    put16(raw + 0xd4, sizeof(rsn));
    memcpy(raw + 0xd6, rsn, sizeof(rsn));
    assert(AICDecodeWCLJoinRequest(raw, sizeof(raw), result));
    assert(result.ssidLength == 4 && memcmp(result.ssid, "test", 4) == 0);
    assert(result.bssid[0] == 2 && result.bssid[5] == 1);
    assert(result.channelSpec == 44 && result.pmk[0] == 0xa5);
    assert(!AICDecodeWCLJoinRequest(nullptr, sizeof(raw), result));
    assert(!AICDecodeWCLJoinRequest(raw, 0x217, result));
    put32(raw + 0x214, 11);
    assert(!AICDecodeWCLJoinRequest(raw, sizeof(raw), result));
    put32(raw + 0x214, 1);
    put32(raw + 0x1c, 33);
    assert(!AICDecodeWCLJoinRequest(raw, sizeof(raw), result));
    put32(raw + 0x1c, 4);
    put32(raw + 0x14, 1u << 12); // WPA3-SAE unsupported.
    assert(!AICDecodeWCLJoinRequest(raw, sizeof(raw), result));
    put32(raw + 0x14, 1u << 3);
    put32(raw + 0x48, 7); // PMKSA not this flow.
    assert(!AICDecodeWCLJoinRequest(raw, sizeof(raw), result));
    put32(raw + 0x48, 6);
    raw[0xd6 + 7] = 2; // TKIP group cipher.
    assert(!AICDecodeWCLJoinRequest(raw, sizeof(raw), result));
    raw[0xd6 + 7] = 4;
    raw[0xd6 + 19] = 1; // 802.1X AKM.
    assert(!AICDecodeWCLJoinRequest(raw, sizeof(raw), result));
    raw[0xd6 + 19] = 2;
    raw[0xd6 + 20] = 0x40; // PMF required.
    assert(!AICDecodeWCLJoinRequest(raw, sizeof(raw), result));
    raw[0xd6 + 20] = 0;
    raw[0x21c] = 3; // Multicast BSSID.
    assert(!AICDecodeWCLJoinRequest(raw, sizeof(raw), result));
    raw[0x21c] = 2;
    put16(raw + 0xd4, 0); // No override: radio service must validate scan RSN.
    assert(AICDecodeWCLJoinRequest(raw, sizeof(raw), result));
    return 0;
}
