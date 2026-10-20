#pragma once

#include <stddef.h>
#include <stdint.h>
#include <string.h>

// Observed macOS 15 WCL ConnectComplete payload. Only one candidate is used.
struct AICWCLConnectionPeer {
    uint8_t bssid[6];
    uint16_t reserved;
    int32_t driverStatus;
    int32_t driverReason;
};

struct AICWCLConnectionEvent {
    uint16_t status;
    uint16_t reason;
    AICWCLConnectionPeer peers[10];
};

static_assert(sizeof(AICWCLConnectionEvent) == 164, "WCL connection event size");

inline AICWCLConnectionEvent AICMakeWCLConnectionEvent(
    const uint8_t bssid[6], bool connected, int32_t driverStatus) {
    AICWCLConnectionEvent event = {};
    event.status = connected ? 0 : 1;
    memcpy(event.peers[0].bssid, bssid, 6);
    event.peers[0].driverStatus = driverStatus;
    return event;
}
