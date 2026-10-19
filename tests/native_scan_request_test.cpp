#include <assert.h>
#include <stdint.h>
#include <string.h>

#include "../native/AICWCLScanRequest.h"

static void put32(uint8_t *data, uint32_t value) {
    for (unsigned i = 0; i < 4; ++i) data[i] = uint8_t(value >> (8 * i));
}

int main() {
    uint8_t raw[kAICWCLScanRequestSize] = {};
    AICWCLScanRequest result = {};
    put32(raw, 42);
    put32(raw + 0x1c, 4);
    memcpy(raw + 0x20, "test", 4);
    put32(raw + 0x40, 1);
    put32(raw + 0x54, 3);
    put32(raw + 0x58 + 4, 6);
    put32(raw + 0x58 + 8, 0x8);
    put32(raw + 0x64 + 4, 44);
    put32(raw + 0x64 + 8, 0x10);
    put32(raw + 0x70 + 4, 7);
    put32(raw + 0x70 + 8, 0x2000); // Ignore 6 GHz overlap.
    assert(AICDecodeWCLScanRequest(raw, sizeof(raw), result));
    assert(result.identifier == 42 && result.type == 1);
    assert(result.ssidLength == 4 && memcmp(result.ssid, "test", 4) == 0);
    assert(result.channelCount == 3);
    assert(result.selectedChannels[6 / 8] & (1u << (6 % 8)));
    assert(result.selectedChannels[44 / 8] & (1u << (44 % 8)));
    assert(!(result.selectedChannels[7 / 8] & (1u << (7 % 8))));
    assert(!AICDecodeWCLScanRequest(nullptr, sizeof(raw), result));
    assert(!AICDecodeWCLScanRequest(raw, 0x57, result));
    assert(!AICDecodeWCLScanRequest(raw, 0x58 + 2 * 12, result));
    put32(raw + 0x1c, 33);
    assert(!AICDecodeWCLScanRequest(raw, sizeof(raw), result));
    put32(raw + 0x1c, 4);
    put32(raw + 0x54, 401);
    assert(!AICDecodeWCLScanRequest(raw, sizeof(raw), result));
    put32(raw + 0x54, 3);
    put32(raw + 0x40, 0);
    assert(!AICDecodeWCLScanRequest(raw, sizeof(raw), result));
    put32(raw + 0x40, 1);
    put32(raw + 0x54, 1);
    put32(raw + 0x58 + 8, 0x2000);
    assert(!AICDecodeWCLScanRequest(raw, sizeof(raw), result));
    return 0;
}
