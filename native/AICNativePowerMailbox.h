#pragma once

#include "AICNativeBridgeProtocol.h"

// Caller serializes access. The latest requested power state remains visible
// until the service publishes matching observed hardware state.
class AICNativePowerMailbox {
public:
    bool request(bool powered, bool observedReady, bool observedPowered) {
        if ((ready && command.value == static_cast<uint32_t>(powered)) ||
            (!ready && observedReady && observedPowered == powered)) {
            return false;
        }
        ++sequence;
        if (sequence == 0) ++sequence;
        command = {kAICNativeBridgeVersion, kAICNativeSetPower,
                   sequence, static_cast<uint32_t>(powered)};
        ready = true;
        return true;
    }

    void observe(bool powered) {
        if (ready && command.value == static_cast<uint32_t>(powered)) {
            ready = false;
        }
    }

    bool read(AICNativeCommand *output) const {
        if (!output || !ready) return false;
        *output = command;
        return true;
    }

private:
    uint32_t sequence = 0;
    AICNativeCommand command = {};
    bool ready = false;
};
