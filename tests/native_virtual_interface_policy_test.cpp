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
    return 0;
}
