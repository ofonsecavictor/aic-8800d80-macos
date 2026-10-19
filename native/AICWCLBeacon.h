#pragma once

#include <stddef.h>
#include <stdint.h>
#include <string.h>

// macOS 15 WCL scan-result metadata, followed by validated 802.11 IE bytes.
// This private ABI is not stable across macOS releases; nothing publishes it
// to the kernel yet. The fixed layout is checked in the offline test.
struct AICWCLBeaconMetadata {
    uint32_t ieLength;
    uint16_t channelSpec;
    uint8_t ssid[32];
    uint8_t ssidLength;
    uint8_t channel;
    uint8_t reserved0;
    uint8_t bssid[6];
    uint8_t reserved1;
    int32_t rssi;
    int16_t noise;
    int16_t snr;
    uint16_t interval;
    uint16_t capability;
    uint32_t flags;
};

static_assert(sizeof(AICWCLBeaconMetadata) == 0x40, "Sequoia WCL beacon size");
static_assert(offsetof(AICWCLBeaconMetadata, bssid) == 0x29, "WCL BSSID offset");
static_assert(offsetof(AICWCLBeaconMetadata, rssi) == 0x30, "WCL RSSI offset");
static_assert(offsetof(AICWCLBeaconMetadata, flags) == 0x3c, "WCL flags offset");

enum { kAICWCLMaxIEBytes = 1024 };

struct AICWCLBeaconInput {
    const uint8_t *ssid;
    size_t ssidLength;
    const uint8_t *bssid;
    uint8_t channel;
    bool fiveGHz;
    int32_t rssi;
    uint16_t interval;
    uint16_t capability;
    const uint8_t *ies;
    size_t ieLength;
};

inline bool AICValidWCLIEs(const uint8_t *ies, size_t length) {
    if (length > kAICWCLMaxIEBytes || (length && !ies)) return false;
    size_t offset = 0;
    while (offset < length) {
        if (length - offset < 2) return false;
        const uint8_t elementType = ies[offset];
        const size_t elementLength = ies[offset + 1];
        offset += 2;
        if (elementLength > length - offset ||
            (elementType == 0 && elementLength > 32)) return false;
        offset += elementLength;
    }
    return true;
}

inline bool AICEncodeWCLBeacon(const AICWCLBeaconInput &input,
                               uint8_t *output, size_t capacity,
                               size_t &written) {
    written = 0;
    bool nonzeroBssid = false;
    if (input.bssid) {
        for (unsigned i = 0; i < 6; ++i) nonzeroBssid |= input.bssid[i] != 0;
    }
    if (!output || !input.bssid || !input.ssid || input.ssidLength > 32 ||
        !input.channel || input.channel > 196 ||
        (input.fiveGHz ? input.channel <= 14 : input.channel > 14) ||
        input.rssi < -127 || input.rssi > 0 || !input.interval ||
        (input.bssid[0] & 1) || !nonzeroBssid ||
        !AICValidWCLIEs(input.ies, input.ieLength) ||
        capacity < sizeof(AICWCLBeaconMetadata) + input.ieLength) {
        return false;
    }
    AICWCLBeaconMetadata metadata = {};
    metadata.ieLength = uint32_t(input.ieLength);
    metadata.channelSpec = uint16_t(input.channel |
        (input.fiveGHz ? 0xd000u : 0x1000u));
    memcpy(metadata.ssid, input.ssid, input.ssidLength);
    metadata.ssidLength = uint8_t(input.ssidLength);
    metadata.channel = input.channel;
    memcpy(metadata.bssid, input.bssid, 6);
    metadata.rssi = input.rssi;
    metadata.interval = input.interval;
    metadata.capability = input.capability;
    metadata.flags = (1u << 1) | (1u << 14); // SSID and RSSI valid.
    memcpy(output, &metadata, sizeof(metadata));
    if (input.ieLength)
        memcpy(output + sizeof(metadata), input.ies, input.ieLength);
    written = sizeof(metadata) + input.ieLength;
    return true;
}
