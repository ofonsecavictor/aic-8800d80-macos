#include "../native/AICNativeAWDLMailbox.h"
#include "../native/AICNativeActionFrame.h"

#include <assert.h>
#include <string.h>

int main() {
    const uint8_t mac[6] = {0x02, 0x11, 0x22, 0x33, 0x44, 0x55};
    AICNativeAWDLMailbox mailbox;
    AICNativeAWDLState state = {};
    assert(!mailbox.read(&state));
    assert(mailbox.publish(mac, true, 149));
    assert(mailbox.read(&state));
    assert(state.enabled == 1 && state.channel == 149 &&
           memcmp(state.mac, mac, 6) == 0);
    assert(!mailbox.read(&state));
    assert(mailbox.publish(mac, false, 149));
    assert(mailbox.read(&state) && state.enabled == 0);
    const uint8_t zero[6] = {};
    assert(!mailbox.publish(zero, true, 149));
    assert(!mailbox.publish(mac, true, 0));

    uint8_t action[40] = {};
    action[0] = 0xd0;
    memcpy(action + 10, mac, 6);
    action[24] = 127;
    AICNativeFrame frame = {};
    assert(AICPrepareActionTransmit(&frame, action, sizeof(action), 7, 1,
                                    149, mac));
    assert(frame.kind == kAICNativeFrameAction && frame.length == 40 &&
           frame.sequence == 7 && frame.vif == 1 && frame.channel == 149);
    action[10] ^= 2;
    assert(!AICPrepareActionTransmit(&frame, action, sizeof(action), 8, 1,
                                     149, mac));
    return 0;
}
