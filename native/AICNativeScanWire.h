#pragma once

#include "AICNativeBridgeProtocol.h"
#include "AICNativeScanMailbox.h"
#include "AICWCLBssCache.h"

inline bool AICEncodeNativeScanRequest(const AICNativeScanTicket &ticket,
                                      AICNativeScanRequest &wire) {
    wire = {};
    if (!ticket.sequence || ticket.request.ssidLength > 32 ||
        ticket.request.channelCount > kAICWCLMaxChannels) return false;
    wire.version = kAICNativeBridgeVersion;
    wire.sequence = ticket.sequence;
    wire.identifier = ticket.request.identifier;
    wire.type = ticket.request.type;
    wire.ssidLength = ticket.request.ssidLength;
    wire.channelCount = ticket.request.channelCount;
    memcpy(wire.ssid, ticket.request.ssid, sizeof(wire.ssid));
    memcpy(wire.bssid, ticket.request.bssid, sizeof(wire.bssid));
    memcpy(wire.selectedChannels, ticket.request.selectedChannels,
           sizeof(wire.selectedChannels));
    return AICNativeScanRequestValid(wire);
}

inline bool AICNativeScanResultValid(const AICNativeScanResult &result) {
    if (result.version != kAICNativeBridgeVersion || !result.sequence ||
        result.length < sizeof(AICWCLBeaconMetadata) ||
        result.length > sizeof(result.data) ||
        !AICValidWCLBeaconPacket(result.data, result.length) ||
        result.beaconLength > sizeof(result.beacon) ||
        (result.beaconLength && !AICWCLBssCache::validBeacon(
            result.data, result.length, result.beacon,
            result.beaconLength))) return false;
    for (uint32_t i = result.length; i < sizeof(result.data); ++i)
        if (result.data[i]) return false;
    for (uint32_t i = result.beaconLength; i < sizeof(result.beacon); ++i)
        if (result.beacon[i]) return false;
    return true;
}
