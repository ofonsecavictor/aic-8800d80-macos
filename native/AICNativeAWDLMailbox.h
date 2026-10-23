#pragma once

#include "AICNativeBridgeProtocol.h"
#include <string.h>

// Protected by the controller state lock. A new record supersedes an older
// unconsumed record because only the latest enable/channel state is actionable.
class AICNativeAWDLMailbox {
public:
    bool publish(const uint8_t mac[6], bool enabled, uint32_t channel) {
        AICNativeAWDLState next = {};
        next.version = kAICNativeBridgeVersion;
        if (++sequence == 0) ++sequence;
        next.sequence = sequence;
        next.enabled = enabled ? 1u : 0u;
        next.channel = channel;
        if (mac) memcpy(next.mac, mac, sizeof(next.mac));
        if (!AICNativeAWDLStateValid(next)) return false;
        state = next;
        pending = true;
        return true;
    }

    bool read(AICNativeAWDLState *output) {
        if (!output || !pending) return false;
        *output = state;
        pending = false;
        return true;
    }

    void clear() {
        memset(&state, 0, sizeof(state));
        pending = false;
    }

private:
    AICNativeAWDLState state = {};
    uint32_t sequence = 0;
    bool pending = false;
};
