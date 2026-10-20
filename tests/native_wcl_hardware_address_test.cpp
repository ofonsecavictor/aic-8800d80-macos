#include <assert.h>
#include <stdint.h>
#include <string.h>

#include "../native/AICWCLHardwareAddress.h"

int main() {
    AICWCLHardwareAddress out = {};
    const uint8_t valid[] = {0x02, 0x11, 0x22, 0x33, 0x44, 0x55};
    assert(AICEncodeWCLHardwareAddress(valid, out));
    assert(out.version == 1 && memcmp(out.address, valid, 6) == 0);
    assert(out.reserved[0] == 0 && out.reserved[1] == 0);
    const uint8_t multicast[] = {0x03, 0x11, 0x22, 0x33, 0x44, 0x55};
    assert(!AICEncodeWCLHardwareAddress(multicast, out));
    assert(out.version == 0);
    const uint8_t zero[6] = {};
    assert(!AICEncodeWCLHardwareAddress(zero, out));
    assert(!AICEncodeWCLHardwareAddress(nullptr, out));
    return 0;
}
