#include <assert.h>
#include <stdint.h>
#include <string.h>

#include "../native/AICWCLBssCache.h"
#include "../native/AICNativeScanWire.h"

int main() {
    AICWCLBssCache cache;
    const uint8_t ssid[] = {'A', 'I', 'C'};
    const uint8_t ies[] = {0, 3, 'A', 'I', 'C', 48, 2, 1, 0};
    uint8_t first[6] = {2, 1, 2, 3, 4, 5};
    uint8_t second[6] = {2, 1, 2, 3, 4, 6};
    uint8_t packet[AICWCLBssCache::kPacketCapacity] = {};
    uint8_t reply[AICWCLBssCache::kReplyCapacity] = {};
    size_t length = 0;
    AICWCLBeaconInput input = {ssid, sizeof(ssid), first, 6, false, -55,
                               100, 0x0011, ies, sizeof(ies)};
    assert(AICEncodeWCLBeacon(input, packet, sizeof(packet), length));
    uint8_t beacon[36 + sizeof(ies)] = {};
    beacon[0] = 0x80;
    memcpy(beacon + 16, first, 6);
    memcpy(beacon + 32, &input.interval, 2);
    memcpy(beacon + 34, &input.capability, 2);
    memcpy(beacon + 36, ies, sizeof(ies));
    AICNativeScanResult result = {};
    result.version = kAICNativeBridgeVersion;
    result.sequence = 1;
    result.length = uint32_t(length);
    memcpy(result.data, packet, length);
    result.beaconLength = sizeof(beacon);
    memcpy(result.beacon, beacon, sizeof(beacon));
    assert(AICNativeScanResultValid(result));
    result.beacon[16] ^= 1;
    assert(!AICNativeScanResultValid(result));
    result.beacon[16] ^= 1;
    assert(cache.remember(packet, length, beacon, sizeof(beacon)));
    assert(!cache.copySelected(reply, sizeof(reply)));
    assert(cache.select(first));
    assert(cache.copySelected(reply, sizeof(reply)));
    uint8_t beaconReply[AICWCLBssCache::kBeaconReplyCapacity] = {};
    assert(cache.copySelectedBeacon(beaconReply, sizeof(beaconReply)));
    uint32_t beaconLength = 0;
    memcpy(&beaconLength, beaconReply, 4);
    assert(beaconLength == sizeof(beacon));
    assert(memcmp(beaconReply + 4, beacon, sizeof(beacon)) == 0);
    beacon[16] ^= 1;
    assert(!cache.remember(packet, length, beacon, sizeof(beacon)));
    beacon[16] ^= 1;
    assert(memcmp(reply, packet, length) == 0);
    for (size_t i = length; i < sizeof(reply); ++i) assert(reply[i] == 0);
    input.bssid = second;
    assert(AICEncodeWCLBeacon(input, packet, sizeof(packet), length));
    assert(cache.remember(packet, length));
    assert(cache.copySelected(reply, sizeof(reply)));
    cache.clearSelected();
    assert(!cache.copySelected(reply, sizeof(reply)));
    assert(cache.select(second));
    assert(cache.copySelected(reply, sizeof(reply)));
    packet[0] = 255;
    assert(!cache.remember(packet, length));
    assert(!cache.select(first + 1));
    return 0;
}
