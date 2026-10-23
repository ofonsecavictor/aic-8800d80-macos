#include "../native/AICNativeVirtualInterfacePolicy.h"

#include <assert.h>

int main() {
    const uint8_t valid[6] = {0x02, 0x11, 0x22, 0x33, 0x44, 0x55};
    const uint8_t multicast[6] = {0x03, 0x11, 0x22, 0x33, 0x44, 0x55};
    const uint8_t zero[6] = {};

    assert(AICSupportsVirtualInterface(kAICVirtualInterfaceRoleAWDL,
                                       valid, sizeof(valid)));
    assert(AICVirtualInterfacePrefix(kAICVirtualInterfaceRoleAWDL));
    assert(!AICSupportsVirtualInterface(3, valid, sizeof(valid)));
    assert(!AICSupportsVirtualInterface(4, valid, sizeof(valid)));
    assert(!AICSupportsVirtualInterface(5, valid, sizeof(valid)));
    assert(!AICSupportsVirtualInterface(7, valid, sizeof(valid)));
    assert(!AICSupportsVirtualInterface(kAICVirtualInterfaceRoleAWDL,
                                        multicast, sizeof(multicast)));
    assert(!AICSupportsVirtualInterface(kAICVirtualInterfaceRoleAWDL,
                                        zero, sizeof(zero)));
    assert(!AICSupportsVirtualInterface(kAICVirtualInterfaceRoleAWDL,
                                        nullptr, sizeof(valid)));
    assert(!AICSupportsVirtualInterface(kAICVirtualInterfaceRoleAWDL,
                                        valid, sizeof(valid) - 1));
    uint8_t derived[6] = {};
    assert(AICDeriveAWDLAddress(valid, sizeof(valid), derived,
                                sizeof(derived)));
    assert(AICValidVirtualInterfaceAddress(derived, sizeof(derived)));
    assert((derived[0] & 0x02) != 0);
    assert(derived[5] == static_cast<uint8_t>(valid[5] ^ 0x80));
    assert(!AICDeriveAWDLAddress(multicast, sizeof(multicast), derived,
                                 sizeof(derived)));
    assert(!AICDeriveAWDLAddress(valid, sizeof(valid), nullptr,
                                 sizeof(derived)));
    assert(!AICDeriveAWDLAddress(valid, sizeof(valid), derived,
                                 sizeof(derived) - 1));
    const uint8_t awdl0[16] = {'a', 'w', 'd', 'l', '0'};
    const uint8_t awdl12[16] = {'a', 'w', 'd', 'l', '1', '2'};
    const uint8_t automatic[16] = {};
    const uint8_t wrongPrefix[16] = {'l', 'l', 'w', '0'};
    const uint8_t missingUnit[16] = {'a', 'w', 'd', 'l'};
    const uint8_t trailingGarbage[16] = {
        'a', 'w', 'd', 'l', '0', 0, 'x'};
    assert(AICValidAWDLInterfaceName(awdl0, sizeof(awdl0)));
    assert(AICValidAWDLInterfaceName(awdl12, sizeof(awdl12)));
    assert(AICValidAWDLInterfaceName(automatic, sizeof(automatic)));
    assert(!AICValidAWDLInterfaceName(wrongPrefix, sizeof(wrongPrefix)));
    assert(!AICValidAWDLInterfaceName(missingUnit, sizeof(missingUnit)));
    assert(!AICValidAWDLInterfaceName(trailingGarbage,
                                      sizeof(trailingGarbage)));
    assert(AICValidAWDLCreateRequest(
        1, kAICVirtualInterfaceRoleAWDL, valid, sizeof(valid),
        awdl0, sizeof(awdl0)));
    assert(!AICValidAWDLCreateRequest(
        2, kAICVirtualInterfaceRoleAWDL, valid, sizeof(valid),
        awdl0, sizeof(awdl0)));
    assert(!AICValidAWDLCreateRequest(
        1, 5, valid, sizeof(valid), awdl0, sizeof(awdl0)));
    assert(AICShouldActivateAttachedAWDL(true, true, true, true));
    assert(!AICShouldActivateAttachedAWDL(false, true, true, true));
    assert(!AICShouldActivateAttachedAWDL(true, false, true, true));
    assert(!AICShouldActivateAttachedAWDL(true, true, false, true));
    assert(!AICShouldActivateAttachedAWDL(true, true, true, false));
    return 0;
}
