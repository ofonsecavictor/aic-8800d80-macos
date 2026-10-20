#pragma once

#include <stdint.h>
#include <string.h>

#include "AICNativeBridgeProtocol.h"

// Caller serializes access. PMK is delivered once, then wiped from the
// mailbox; an unfinished operation still retains its sequence and deadline.
class AICNativeJoinMailbox {
public:
    static constexpr uint64_t kTimeoutMillis = 30000;

    bool begin(const AICWCLJoinRequest &join, uint64_t nowMillis,
               uint32_t *newSequence) {
        if (!newSequence || pending || nowMillis > UINT64_MAX - kTimeoutMillis)
            return false;
        if (++sequence == 0) ++sequence;
        AICNativeJoinRequest request = {};
        request.version = kAICNativeBridgeVersion;
        request.sequence = sequence;
        request.ssidLength = join.ssidLength;
        request.channelSpec = join.channelSpec;
        request.rsnLength = join.rsnLength;
        memcpy(request.ssid, join.ssid, sizeof(request.ssid));
        memcpy(request.bssid, join.bssid, sizeof(request.bssid));
        memcpy(request.pmk, join.pmk, sizeof(request.pmk));
        memcpy(request.rsn, join.rsn, sizeof(request.rsn));
        if (!AICNativeJoinRequestValid(request)) {
            wipe(&request, sizeof(request));
            return false;
        }
        current = request;
        memcpy(targetBSSID, request.bssid, sizeof(targetBSSID));
        wipe(&request, sizeof(request));
        deadline = nowMillis + kTimeoutMillis;
        pending = true;
        delivered = false;
        *newSequence = sequence;
        return true;
    }

    bool take(AICNativeJoinRequest *request, uint64_t nowMillis) {
        if (!request || !pending || delivered || nowMillis >= deadline)
            return false;
        *request = current;
        wipe(&current, sizeof(current));
        delivered = true;
        return true;
    }

    bool finish(uint32_t finishedSequence, uint64_t nowMillis) {
        if (!pending || !delivered || finishedSequence != sequence ||
            nowMillis >= deadline) return false;
        clear();
        return true;
    }

    bool abort(uint32_t *abortedSequence) {
        if (!pending) return false;
        if (abortedSequence) *abortedSequence = sequence;
        clear();
        return true;
    }

    bool expire(uint64_t nowMillis, uint32_t *expiredSequence) {
        if (!pending || nowMillis < deadline) return false;
        if (expiredSequence) *expiredSequence = sequence;
        clear();
        return true;
    }

    bool active() const { return pending; }
    bool target(uint8_t bssid[6]) const {
        if (!pending || !bssid) return false;
        memcpy(bssid, targetBSSID, sizeof(targetBSSID));
        return true;
    }

private:
    static void wipe(void *buffer, size_t length) {
        volatile uint8_t *p = static_cast<volatile uint8_t *>(buffer);
        while (length--) *p++ = 0;
    }
    void clear() {
        wipe(&current, sizeof(current));
        wipe(targetBSSID, sizeof(targetBSSID));
        pending = delivered = false;
        deadline = 0;
    }

    AICNativeJoinRequest current = {};
    uint8_t targetBSSID[6] = {};
    uint64_t deadline = 0;
    uint32_t sequence = 0;
    bool pending = false;
    bool delivered = false;
};
