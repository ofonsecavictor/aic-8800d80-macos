#include <assert.h>
#include <stdint.h>

#include "../native/AICNativeScanWire.h"

int main() {
    AICNativeScanMailbox mailbox;
    AICNativeScanTicket ticket = {};
    AICWCLScanRequest request = {};
    request.type = 1;
    request.ssidLength = 3;
    request.ssid[0] = 'A';
    request.ssid[1] = 'I';
    request.ssid[2] = 'C';
    request.channelCount = 1;
    request.selectedChannels[44 / 8] = uint8_t(1u << (44 % 8));
    assert(mailbox.begin(request, 1000, &ticket));
    assert(ticket.sequence != 0 && ticket.request.ssidLength == 3);
    assert(!mailbox.begin(request, 1001, &ticket));
    AICNativeScanTicket read = {};
    assert(mailbox.read(&read) && read.sequence == ticket.sequence);
    AICNativeScanRequest wire = {};
    assert(AICEncodeNativeScanRequest(read, wire));
    assert(wire.version == kAICNativeBridgeVersion);
    assert(wire.sequence == ticket.sequence && wire.ssidLength == 3);
    const uint8_t ssid[] = {'A', 'I', 'C'};
    const uint8_t bssid[] = {0x02, 0x11, 0x22, 0x33, 0x44, 0x55};
    const uint8_t ies[] = {0, 3, 'A', 'I', 'C'};
    AICWCLBeaconInput beacon = {ssid, sizeof(ssid), bssid, 44, true, -55,
                                100, 0x0011, ies, sizeof(ies)};
    uint8_t packet[sizeof(AICWCLBeaconMetadata) + sizeof(ies)] = {};
    size_t written = 0;
    assert(AICEncodeWCLBeacon(beacon, packet, sizeof(packet), written));
    assert(!mailbox.acceptResult(ticket.sequence + 1, packet, written, 1002));
    assert(!mailbox.acceptResult(ticket.sequence, packet, written - 1, 1002));
    packet[offsetof(AICWCLBeaconMetadata, ssid)] = 'X';
    assert(!mailbox.acceptResult(ticket.sequence, packet, written, 1002));
    packet[offsetof(AICWCLBeaconMetadata, ssid)] = 'A';
    assert(mailbox.acceptResult(ticket.sequence, packet, written, 1002));
    AICNativeScanResult result = {};
    result.version = kAICNativeBridgeVersion;
    result.sequence = ticket.sequence;
    result.length = static_cast<uint32_t>(written);
    memcpy(result.data, packet, written);
    assert(AICNativeScanResultValid(result));
    result.data[written] = 1;
    assert(!AICNativeScanResultValid(result));
    assert(mailbox.resultCount() == 1);
    assert(!mailbox.finish(ticket.sequence + 1, 1003));
    assert(mailbox.finish(ticket.sequence, 1003));
    assert(!mailbox.read(&read));
    assert(!mailbox.acceptResult(ticket.sequence, packet, written, 1004));

    assert(mailbox.begin(request, 2000, &ticket));
    const uint32_t secondSequence = ticket.sequence;
    assert(!mailbox.acceptResult(secondSequence, packet, written, 22000));
    assert(!mailbox.finish(secondSequence, 22000));
    uint32_t expired = 0;
    assert(mailbox.expire(22000, &expired) && expired == secondSequence);
    assert(!mailbox.read(&read));

    assert(mailbox.begin(request, 23000, &ticket));
    uint32_t aborted = 0;
    assert(mailbox.abort(&aborted) && aborted == ticket.sequence);
    assert(!mailbox.finish(aborted, 23001));
    return 0;
}
