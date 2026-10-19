#pragma once

#include "AICNativeBridgeProtocol.h"

// A bounded in-memory handoff. Caller holds the controller's state lock.
// No frame is persisted; a full queue rejects new frames rather than silently
// replacing a packet that the other side has not consumed.
class AICNativeFrameMailbox {
public:
    static constexpr unsigned kCapacity = 8;

    bool push(const AICNativeFrame &frame, bool fromService) {
        if (!AICNativeFrameValid(frame, fromService) || count == kCapacity)
            return false;
        frames[tail] = frame;
        tail = (tail + 1) % kCapacity;
        ++count;
        return true;
    }

    bool pop(AICNativeFrame *frame) {
        if (!frame || !count) return false;
        *frame = frames[head];
        frames[head] = {};
        head = (head + 1) % kCapacity;
        --count;
        return true;
    }

    unsigned size() const { return count; }

private:
    AICNativeFrame frames[kCapacity] = {};
    unsigned head = 0;
    unsigned tail = 0;
    unsigned count = 0;
};
