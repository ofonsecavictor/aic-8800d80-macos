#pragma once

#include <stdint.h>

#include "AICWCLBeacon.h"
#include "AICWCLScanRequest.h"

// Caller serializes access. No kernel messages or USB operations occur here.
// A request stays readable until completion so a restarted service can retry
// it, but sequence matching rejects stale results from an earlier scan.
struct AICNativeScanTicket {
    uint32_t sequence;
    AICWCLScanRequest request;
};

class AICNativeScanMailbox {
public:
    static constexpr uint64_t kTimeoutMillis = 20000;

    bool begin(const AICWCLScanRequest &request, uint64_t nowMillis,
               AICNativeScanTicket *ticket) {
        if (!ticket || pending || nowMillis > UINT64_MAX - kTimeoutMillis ||
            request.ssidLength > 32 || request.channelCount > kAICWCLMaxChannels ||
            request.type < 1 || request.type > 4) return false;
        ++sequence;
        if (sequence == 0) ++sequence;
        current = {sequence, request};
        deadline = nowMillis + kTimeoutMillis;
        results = 0;
        pending = true;
        *ticket = current;
        return true;
    }

    bool read(AICNativeScanTicket *ticket) const {
        if (!ticket || !pending) return false;
        *ticket = current;
        return true;
    }

    bool acceptResult(uint32_t resultSequence, const void *packet, size_t length,
                      uint64_t nowMillis) {
        if (!pending || resultSequence != sequence || nowMillis >= deadline ||
            results >= kMaxResults || !AICValidWCLBeaconPacket(packet, length))
            return false;
        AICWCLBeaconMetadata metadata = {};
        memcpy(&metadata, packet, sizeof(metadata));
        if (current.request.channelCount &&
            !(current.request.selectedChannels[metadata.channel / 8] &
              (1u << (metadata.channel % 8)))) return false;
        if (current.request.type != 2 && current.request.ssidLength &&
            (metadata.ssidLength != current.request.ssidLength ||
             memcmp(metadata.ssid, current.request.ssid,
                    current.request.ssidLength) != 0)) return false;
        bool allZero = true, allBroadcast = true;
        for (unsigned i = 0; i < 6; ++i) {
            allZero &= current.request.bssid[i] == 0;
            allBroadcast &= current.request.bssid[i] == 0xff;
        }
        if (!allZero && !allBroadcast &&
            memcmp(metadata.bssid, current.request.bssid, 6) != 0) return false;
        ++results;
        return true;
    }

    bool finish(uint32_t finishedSequence, uint64_t nowMillis) {
        if (!pending || finishedSequence != sequence || nowMillis >= deadline)
            return false;
        pending = false;
        return true;
    }

    bool abort(uint32_t *abortedSequence) {
        if (!pending) return false;
        if (abortedSequence) *abortedSequence = sequence;
        pending = false;
        return true;
    }

    bool expire(uint64_t nowMillis, uint32_t *expiredSequence) {
        if (!pending || nowMillis < deadline) return false;
        if (expiredSequence) *expiredSequence = sequence;
        pending = false;
        return true;
    }

    uint32_t resultCount() const { return results; }

private:
    static constexpr uint32_t kMaxResults = 256;
    AICNativeScanTicket current = {};
    uint64_t deadline = 0;
    uint32_t sequence = 0;
    uint32_t results = 0;
    bool pending = false;
};
