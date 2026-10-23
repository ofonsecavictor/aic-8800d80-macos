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

inline bool AICDeriveAWDLAddress(const uint8_t *station, size_t stationLength,
                                 uint8_t *awdl, size_t awdlLength) {
    if (!awdl || awdlLength != 6 ||
        !AICValidVirtualInterfaceAddress(station, stationLength)) return false;
    for (size_t index = 0; index < awdlLength; ++index) awdl[index] = station[index];
    awdl[0] = static_cast<uint8_t>((awdl[0] | 0x02) & 0xfe);
    awdl[5] ^= 0x80;
    return AICValidVirtualInterfaceAddress(awdl, awdlLength);
}

inline const char *AICVirtualInterfacePrefix(uint32_t role) {
    return role == kAICVirtualInterfaceRoleAWDL ? "awdl" : nullptr;
}

inline bool AICValidAWDLInterfaceName(const uint8_t *name, size_t length) {
    if (!name || length < 5) return false;
    bool allZero = true;
    for (size_t index = 0; index < length; ++index)
        allZero &= name[index] == 0;
    if (allZero) return true; // Let IO80211's namer select awdl0.
    if (name[0] != 'a' || name[1] != 'w' || name[2] != 'd' ||
        name[3] != 'l') return false;
    size_t index = 4;
    bool hasUnit = false;
    while (index < length && name[index]) {
        if (name[index] < '0' || name[index] > '9') return false;
        hasUnit = true;
        ++index;
    }
    if (!hasUnit || index == length) return false;
    while (index < length) {
        if (name[index++] != 0) return false;
    }
    return true;
}

inline bool AICValidAWDLCreateRequest(uint32_t requestVersion, uint32_t role,
                                      const uint8_t *address,
                                      size_t addressLength,
                                      const uint8_t *name,
                                      size_t nameLength) {
    return requestVersion == 1 &&
           AICSupportsVirtualInterface(role, address, addressLength) &&
           AICValidAWDLInterfaceName(name, nameLength);
}

// A WCL-originated interface is enabled later by macOS.  The delayed fallback
// has no such caller, so leaving it merely attached publishes an AirLink
// IOService without creating a usable awdl0 interface.
inline bool AICShouldActivateAttachedAWDL(bool automatic,
                                          bool attachedSuccessfully,
                                          bool returnedInterface,
                                          bool controllerOwnsInterface) {
    return automatic && attachedSuccessfully && returnedInterface &&
           controllerOwnsInterface;
}
