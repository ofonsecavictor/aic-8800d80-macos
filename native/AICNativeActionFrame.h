#pragma once

#include "AICNativeBridgeProtocol.h"
#include <string.h>

inline bool AICPrepareActionTransmit(AICNativeFrame *output,
                                     const uint8_t *payload, size_t length,
                                     uint32_t sequence, uint32_t vif,
                                     uint32_t channel,
                                     const uint8_t sourceMac[6]) {
    if (!output || !payload || !sourceMac || length > kAICNativeFrameMaxBytes)
        return false;
    AICNativeFrame frame = {};
    frame.version = kAICNativeBridgeVersion;
    frame.kind = kAICNativeFrameAction;
    frame.sequence = sequence;
    frame.vif = vif;
    frame.channel = channel;
    frame.length = static_cast<uint32_t>(length);
    memcpy(frame.data, payload, length);
    // Address 2 is the transmitter address in the supported 24-byte action
    // header. Never let a virtual interface submit another interface's MAC.
    if (length < 16 || memcmp(frame.data + 10, sourceMac, 6) != 0 ||
        !AICNativeFrameValid(frame, false)) return false;
    *output = frame;
    return true;
}
