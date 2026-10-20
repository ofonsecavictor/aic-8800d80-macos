#pragma once

#include "AICNativeBridgeProtocol.h"

// Serialized by the controller command gate. A leave command is delivered
// once; duplicate WCL requests coalesce until the service consumes it.
class AICNativeLeaveMailbox {
public:
    void request() {
        if (pending) return;
        if (++sequence == 0) ++sequence;
        command = {kAICNativeBridgeVersion, kAICNativeLeave, sequence, 0};
        pending = true;
    }

    bool take(AICNativeCommand *out) {
        if (!out || !pending) return false;
        *out = command;
        command = {};
        pending = false;
        return true;
    }

    void clear() {
        command = {};
        pending = false;
    }

private:
    AICNativeCommand command = {};
    uint32_t sequence = 0;
    bool pending = false;
};
