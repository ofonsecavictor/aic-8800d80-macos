#include "../native/AICNativeBridgeProtocol.h"

#include <assert.h>

int main() {
    AICNativeRadioState state = {};
    state.version = kAICNativeBridgeVersion;
    assert(AICNativeRadioStateValid(state));

    state.powered = 1;
    state.associated = 1;
    state.channel = 6;
    state.rssi_dbm = -65;
    assert(AICNativeRadioStateValid(state));

    state.version = 2;
    assert(!AICNativeRadioStateValid(state));
    state.version = kAICNativeBridgeVersion;
    state.reserved = 1;
    assert(!AICNativeRadioStateValid(state));
    state.reserved = 0;
    state.channel = 197;
    assert(!AICNativeRadioStateValid(state));
    state.channel = 0;
    assert(!AICNativeRadioStateValid(state));
    state.channel = 6;
    state.powered = 0;
    assert(!AICNativeRadioStateValid(state));
    state.powered = 1;
    state.rssi_dbm = -128;
    assert(!AICNativeRadioStateValid(state));
    return 0;
}
