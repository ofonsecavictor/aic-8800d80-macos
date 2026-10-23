#pragma once

#include "AICNativeBridgeProtocol.h"

// A bounded in-memory handoff. Caller holds the controller's state lock.
// No frame is persisted; a full queue rejects new frames rather than silently
// replacing a packet that the other side has not consumed.
template <unsigned Capacity>
class AICNativeFrameMailboxSized {
public:
    static_assert(Capacity > 0 && Capacity <= 256, "bounded frame mailbox");
    static constexpr unsigned kCapacity = Capacity;

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
    unsigned available() const { return Capacity - count; }

    void clear() {
        for (unsigned i = 0; i < kCapacity; ++i) frames[i] = {};
        head = tail = count = 0;
    }

private:
    AICNativeFrame frames[kCapacity] = {};
    unsigned head = 0;
    unsigned tail = 0;
    unsigned count = 0;
};

// Only outbound BSD traffic needs room for the bursts produced by browsers.
// Keep the inbound control/action-frame queue small.
using AICNativeFrameMailbox = AICNativeFrameMailboxSized<8>;
using AICNativeTransmitMailbox = AICNativeFrameMailboxSized<256>;
