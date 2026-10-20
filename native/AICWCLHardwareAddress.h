#pragma once

#include <stddef.h>
#include <stdint.h>
#include <string.h>

// Observed Sequoia WCL getHW_ADDR payload. Keep this private-ABI layout
// isolated from the radio state and reject invalid station addresses.
struct AICWCLHardwareAddress {
    uint32_t version;
    uint8_t address[6];
    uint8_t reserved[2];
};

static_assert(sizeof(AICWCLHardwareAddress) == 12, "WCL MAC payload size");
static_assert(offsetof(AICWCLHardwareAddress, address) == 4,
              "WCL MAC payload offset");

inline bool AICEncodeWCLHardwareAddress(const uint8_t *mac,
                                       AICWCLHardwareAddress &out) {
    out = {};
    if (!mac || (mac[0] & 1)) return false;
    bool nonzero = false;
    for (unsigned i = 0; i < 6; ++i) nonzero |= mac[i] != 0;
    if (!nonzero) return false;
    out.version = 1;
    memcpy(out.address, mac, 6);
    return true;
}
