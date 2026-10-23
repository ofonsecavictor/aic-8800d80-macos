#pragma once

#include "AICWCLBeacon.h"

// WCL asks for the selected BSS synchronously after LinkStatus. Retain the
// validated scan metadata and IEs; never synthesize a beacon for this query.
class AICWCLBssCache {
public:
    static constexpr size_t kPacketCapacity = sizeof(AICWCLBeaconMetadata) +
                                               kAICWCLMaxIEBytes;
    static constexpr size_t kReplyCapacity = sizeof(AICWCLBeaconMetadata) +
                                              0x800;
    static constexpr size_t kBeaconCapacity = 2048;
    static constexpr size_t kBeaconReplyCapacity = 0x808;
    static constexpr unsigned kEntries = 8;

    static bool validBeacon(const void *packet, size_t length,
                            const void *frame, size_t frameLength) {
        if (!AICValidWCLBeaconPacket(packet, length) || !frame ||
            frameLength < 36 || frameLength > kBeaconCapacity) return false;
        AICWCLBeaconMetadata metadata = {};
        memcpy(&metadata, packet, sizeof(metadata));
        const auto *bytes = static_cast<const uint8_t *>(frame);
        return bytes[0] == 0x80 && (bytes[1] & 0x40) == 0 &&
            memcmp(bytes + 16, metadata.bssid, 6) == 0 &&
            frameLength - 36 == metadata.ieLength &&
            memcmp(bytes + 32, &metadata.interval, 2) == 0 &&
            memcmp(bytes + 34, &metadata.capability, 2) == 0 &&
            memcmp(bytes + 36,
                   static_cast<const uint8_t *>(packet) + sizeof(metadata),
                   metadata.ieLength) == 0;
    }

    bool remember(const void *packet, size_t length,
                  const void *beacon = nullptr, size_t beaconLength = 0) {
        if (!AICValidWCLBeaconPacket(packet, length)) return false;
        if (beaconLength && !validBeacon(packet, length, beacon, beaconLength))
            return false;
        AICWCLBeaconMetadata metadata = {};
        memcpy(&metadata, packet, sizeof(metadata));
        unsigned slot = next;
        bool sameBssid = false;
        for (unsigned i = 0; i < kEntries; ++i) {
            if (entries[i].length &&
                memcmp(entries[i].bssid, metadata.bssid, 6) == 0) {
                slot = i;
                sameBssid = true;
                break;
            }
        }
        if (slot == next) next = (next + 1) % kEntries;
        Entry &entry = entries[slot];
        // A probe response can refresh the scan list, but must not detach
        // the selected BSS metadata from its actual cached beacon frame.
        if (sameBssid && !beaconLength && entry.beaconLength) return true;
        if (!sameBssid) entry.beaconLength = 0;
        entry.length = length;
        memcpy(entry.bssid, metadata.bssid, 6);
        memcpy(entry.packet, packet, length);
        if (beaconLength) {
            entry.beaconLength = beaconLength;
            memcpy(entry.beacon, beacon, beaconLength);
        }
        return true;
    }

    bool select(const uint8_t bssid[6]) {
        clearSelected();
        if (!bssid) return false;
        for (const Entry &entry : entries) {
            if (entry.length && memcmp(entry.bssid, bssid, 6) == 0) {
                selected = entry;
                return true;
            }
        }
        return false;
    }

    bool copySelected(void *reply, size_t capacity) const {
        if (!reply || capacity < kReplyCapacity || !selected.length)
            return false;
        memset(reply, 0, kReplyCapacity);
        memcpy(reply, selected.packet, selected.length);
        return true;
    }

    bool copySelectedBeacon(void *reply, size_t capacity) const {
        if (!reply || capacity < kBeaconReplyCapacity ||
            !selected.length || !selected.beaconLength) return false;
        memset(reply, 0, kBeaconReplyCapacity);
        const uint32_t length = uint32_t(selected.beaconLength);
        memcpy(reply, &length, sizeof(length));
        memcpy(static_cast<uint8_t *>(reply) + 4, selected.beacon,
               selected.beaconLength);
        return true;
    }

    void clearSelected() { selected.length = 0; }

private:
    struct Entry {
        size_t length = 0;
        uint8_t bssid[6] = {};
        uint8_t packet[kPacketCapacity] = {};
        size_t beaconLength = 0;
        uint8_t beacon[kBeaconCapacity] = {};
    };
    Entry entries[kEntries] = {};
    Entry selected = {};
    unsigned next = 0;
};

static_assert(AICWCLBssCache::kReplyCapacity == 0x840,
              "macOS 15 WCL BSS reply capacity");
