#pragma once

#include <stddef.h>
#include <stdint.h>

// apple80211_virtual_interface_type on macOS 13 and newer. Keep the private
// ABI value outside the policy so the kernel translation unit can assert it
// against the pinned macOS 15 header at compile time.
enum : uint32_t {
    kAICVirtualInterfaceRoleAWDL = 6,
};

inline bool AICValidVirtualInterfaceAddress(const uint8_t *address,
                                             size_t length) {
    if (!address || length != 6 || (address[0] & 1)) return false;
    bool nonzero = false;
    for (size_t index = 0; index < length; ++index)
        nonzero |= address[index] != 0;
    return nonzero;
}

inline bool AICSupportsVirtualInterface(uint32_t role,
                                        const uint8_t *address,
                                        size_t length) {
    return role == kAICVirtualInterfaceRoleAWDL &&
           AICValidVirtualInterfaceAddress(address, length);
}

inline const char *AICVirtualInterfacePrefix(uint32_t role) {
    return role == kAICVirtualInterfaceRoleAWDL ? "awdl" : nullptr;
}
