#include "../native/AICNativeBridgeProtocol.h"
#include "../native/AICNativePowerMailbox.h"

#include <assert.h>

int main() {
    AICNativeRadioState state = {};
    state.version = kAICNativeBridgeVersion;
    assert(AICNativeRadioStateValid(state));

    state.powered = 1;
    state.associated = 1;
    state.channel = 6;
    state.rssi_dbm = -65;
    assert(AICNativeRadioStateValid(state));

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
