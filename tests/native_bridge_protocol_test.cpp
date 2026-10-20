#include "../native/AICNativeBridgeProtocol.h"
#include "../native/AICNativePowerMailbox.h"
#include "../native/AICNativeFrameMailbox.h"
#include "../native/AICNativeCapabilityBits.h"

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
    assert(!AICNativeCommandValid(command));

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
