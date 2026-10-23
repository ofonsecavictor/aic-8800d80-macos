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

struct AICWCLFirstBeaconEvent {
    uint16_t status;
    uint16_t reason;
    AICWCLConnectionPeer peer;
};
static_assert(sizeof(AICWCLFirstBeaconEvent) == 20,
              "WCL first-beacon event size");

inline AICWCLFirstBeaconEvent AICMakeWCLFirstBeaconEvent(
    const uint8_t bssid[6]) {
    AICWCLFirstBeaconEvent event = {};
    memcpy(event.peer.bssid, bssid, sizeof(event.peer.bssid));
    return event;
}

// macOS 15 WCL LinkStatus notification (message 216). ConnectComplete alone
// leaves NET_MANAGER in LINK_DOWN even after WPA2 authentication succeeds.
struct AICWCLLinkStatusEvent {
    uint8_t bssid[6];
    uint8_t up;
    uint8_t inSleep;
    uint32_t reason;
    uint32_t reserved;
};
static_assert(sizeof(AICWCLLinkStatusEvent) == 16,
              "WCL link status event size");
static_assert(offsetof(AICWCLLinkStatusEvent, up) == 6,
              "WCL link status up offset");

inline AICWCLLinkStatusEvent AICMakeWCLLinkStatusEvent(
    const uint8_t bssid[6], bool up) {
    AICWCLLinkStatusEvent event = {};
    memcpy(event.bssid, bssid, sizeof(event.bssid));
    event.up = up ? 1 : 0;
    event.reason = 255;
    return event;
}

inline AICWCLConnectionEvent AICMakeWCLConnectionEvent(
    const uint8_t bssid[6], bool connected, int32_t driverStatus) {
    AICWCLConnectionEvent event = {};
    event.status = connected ? 0 : 1;
    memcpy(event.peers[0].bssid, bssid, 6);
    event.peers[0].driverStatus = driverStatus;
    return event;
}
