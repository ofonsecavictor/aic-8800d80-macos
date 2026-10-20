#include "../native/AICNativeBridgeProtocol.h"
#include "../native/AICNativePowerMailbox.h"
#include "../native/AICNativeFrameMailbox.h"
#include "../native/AICNativeCapabilityBits.h"
#include "../native/AICNativeLeaveMailbox.h"
#include "../native/AICWCLConnectionEvent.h"

#include <assert.h>

int main() {
    uint8_t capabilities[19] = {};
    assert(AICSetNativeCapability(capabilities, sizeof(capabilities), 3));
    assert(AICSetNativeCapability(capabilities, sizeof(capabilities), 14));
    assert(capabilities[0] == 0x08 && capabilities[1] == 0x40);
    assert(!AICSetNativeCapability(capabilities, sizeof(capabilities), 152));

    AICNativeRadioState state = {};
    state.version = kAICNativeBridgeVersion;
    state.mac[0] = 0x02;
    state.mac[5] = 0x01;
    assert(AICNativeRadioStateValid(state));

    state.powered = 1;
    state.associated = 1;
    state.channel = 6;
    state.rssi_dbm = -65;
    state.bssid[0] = 0x02;
    state.bssid[5] = 0x02;
    assert(AICNativeRadioStateValid(state));

    state.mac[0] = 0x03;
    assert(!AICNativeRadioStateValid(state));
    state.mac[0] = 0x02;
    state.bssid[0] = 0x03;
    assert(!AICNativeRadioStateValid(state));
    state.bssid[0] = 0x02;
    state.associated = 0;
    assert(!AICNativeRadioStateValid(state));
    state.associated = 1;

    state.version = 1;
    assert(!AICNativeRadioStateValid(state));
    state.version = kAICNativeBridgeVersion;
    state.reserved = 1;
    assert(!AICNativeRadioStateValid(state));
    state.reserved = 0;
    state.channel = 197;
    assert(!AICNativeRadioStateValid(state));
    state.channel = 0;
    assert(!AICNativeRadioStateValid(state));
    state.channel = 6;
    state.powered = 0;
    assert(!AICNativeRadioStateValid(state));
    state.powered = 1;
    state.rssi_dbm = -128;
    assert(!AICNativeRadioStateValid(state));
    state.rssi_dbm = -65;
    state.mac[0] = 0;
    state.mac[5] = 0;
    assert(!AICNativeRadioStateValid(state));

    AICNativeCommand command = {kAICNativeBridgeVersion,
                                kAICNativeSetPower, 1, 0};
    assert(AICNativeCommandValid(command));
    command.value = 1;
    assert(AICNativeCommandValid(command));
    command.value = 2;
    assert(!AICNativeCommandValid(command));
    command.value = 0;
    command.sequence = 0;
    assert(!AICNativeCommandValid(command));
    command.sequence = 1;
    command.operation = 2;
    assert(AICNativeCommandValid(command));
    command.value = 1;
    assert(!AICNativeCommandValid(command));
    command.value = 0;
    command.operation = 3;
    assert(!AICNativeCommandValid(command));

    AICNativeLeaveMailbox leave;
    AICNativeCommand leaveCommand = {};
    assert(!leave.take(&leaveCommand));
    leave.request();
    leave.request();
    assert(leave.take(&leaveCommand));
    assert(AICNativeCommandValid(leaveCommand));
    assert(leaveCommand.operation == kAICNativeLeave);
    const uint32_t firstLeave = leaveCommand.sequence;
    assert(!leave.take(&leaveCommand));
    leave.request();
    assert(leave.take(&leaveCommand) && leaveCommand.sequence != firstLeave);
    leave.request();
    leave.clear();
    assert(!leave.take(&leaveCommand));

    AICNativeScanRequest scan = {};
    scan.version = kAICNativeBridgeVersion;
    scan.sequence = 7;
    scan.type = 1;
    scan.channelCount = 1;
    scan.selectedChannels[44 / 8] = uint8_t(1u << (44 % 8));
    assert(AICNativeScanRequestValid(scan));
    scan.ssidLength = 1;
    scan.ssid[1] = 'X';
    assert(!AICNativeScanRequestValid(scan));
    scan.ssid[1] = 0;
    scan.reserved[0] = 1;
    assert(!AICNativeScanRequestValid(scan));
    scan.reserved[0] = 0;
    scan.selectedChannels[44 / 8] = 0;
    assert(!AICNativeScanRequestValid(scan));
    scan.channelCount = 0;
    assert(AICNativeScanRequestValid(scan));

    AICNativeScanCompletion completion = {kAICNativeBridgeVersion, 7, 0, 0};
    assert(AICNativeScanCompletionValid(completion));
    completion.reserved = 1;
    assert(!AICNativeScanCompletionValid(completion));

    AICNativeJoinRequest join = {};
    join.version = kAICNativeBridgeVersion;
    join.sequence = 8;
    join.ssidLength = 4;
    join.ssid[0] = 't';
    join.channelSpec = 0xd02c;
    join.bssid[0] = 2;
    join.bssid[5] = 1;
    assert(AICNativeJoinRequestValid(join));
    join.ssid[5] = 'X';
    assert(!AICNativeJoinRequestValid(join));
    join.ssid[5] = 0;
    join.bssid[0] = 3;
    assert(!AICNativeJoinRequestValid(join));
    join.bssid[0] = 2;
    AICNativeJoinCompletion joined = {kAICNativeBridgeVersion, 8, 0, 0};
    assert(AICNativeJoinCompletionValid(joined));
    joined.reserved = 1;
    assert(!AICNativeJoinCompletionValid(joined));
    const AICWCLConnectionEvent event = AICMakeWCLConnectionEvent(
        join.bssid, true, 0);
    assert(event.status == 0 && event.peers[0].bssid[5] == 1);

    AICNativeFrame frame = {};
    frame.version = kAICNativeBridgeVersion;
    frame.kind = kAICNativeFrameEthernet;
    frame.sequence = 1;
    frame.vif = 0;
    frame.length = 14;
    assert(AICNativeFrameValid(frame, true));
    assert(AICNativeFrameValid(frame, false));
    frame.vif = 0xff;
    assert(!AICNativeFrameValid(frame, true));
    frame.vif = 1;
    assert(!AICNativeFrameValid(frame, true));
    frame.vif = 0xff;
    frame.kind = kAICNativeFrameAction;
    frame.length = 40;
    frame.channel = 44;
    frame.data[0] = 0xd0;
    frame.data[24] = 127;
    assert(AICNativeFrameValid(frame, true));
    assert(!AICNativeFrameValid(frame, false));
    frame.vif = 1;
    assert(AICNativeFrameValid(frame, false));
    frame.data[24] = 3;
    assert(AICNativeFrameValid(frame, true));
    assert(!AICNativeFrameValid(frame, false));
    frame.data[1] = 0x40;
    assert(!AICNativeFrameValid(frame, true));

    AICNativeFrameMailbox frames;
    AICNativeFrame output = {};
    assert(!frames.pop(&output));
    frame.data[1] = 0;
    frame.data[24] = 127;
    for (unsigned i = 0; i < AICNativeFrameMailbox::kCapacity; ++i) {
        frame.sequence = i + 1;
        assert(frames.push(frame, true));
    }
    assert(frames.size() == AICNativeFrameMailbox::kCapacity);
    assert(!frames.push(frame, true));
    for (unsigned i = 0; i < AICNativeFrameMailbox::kCapacity; ++i) {
        assert(frames.pop(&output));
        assert(output.sequence == i + 1);
    }
    assert(frames.size() == 0);
    assert(!frames.pop(&output));
    assert(frames.push(frame, true));
    frames.clear();
    assert(frames.size() == 0 && !frames.pop(&output));
    frame.data[40] = 1;
    assert(!AICNativeFrameValid(frame, true));

    AICNativePowerMailbox mailbox;
    assert(!mailbox.read(&command));
    assert(mailbox.request(true, true, false));
    assert(mailbox.read(&command));
    const uint32_t onSequence = command.sequence;
    assert(command.value == 1);
    assert(!mailbox.request(true, true, false));
    assert(mailbox.read(&command) && command.sequence == onSequence);
    mailbox.observe(false);
    assert(mailbox.read(&command));  // No false acknowledgement.
    assert(mailbox.request(false, true, false));
    assert(mailbox.read(&command) && command.value == 0);
    assert(command.sequence != onSequence);
    mailbox.observe(false);
    assert(!mailbox.read(&command));
    assert(!mailbox.request(false, true, false));
    return 0;
}
