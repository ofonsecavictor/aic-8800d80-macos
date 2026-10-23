#include <assert.h>
#include <stdint.h>
#include <string.h>

#include "../native/AICNativeJoinMailbox.h"

int main() {
    AICWCLJoinRequest join = {};
    join.ssidLength = 4;
    memcpy(join.ssid, "test", 4);
    join.bssid[0] = 2;
    join.bssid[5] = 1;
    join.channelSpec = 0xd02c;
    memset(join.pmk, 0xa5, 32); // Synthetic PMK only.
    const uint8_t stationMac[6] = {2, 1, 2, 3, 4, 5};

    AICNativeJoinMailbox mailbox;
    AICNativeJoinRequest delivered = {};
    uint32_t sequence = 0;
    assert(mailbox.begin(join, stationMac, 100, &sequence));
    assert(sequence && mailbox.active());
    assert(!mailbox.begin(join, stationMac, 100, &sequence));
    assert(!mailbox.take(nullptr, 101));
    assert(mailbox.take(&delivered, 101));
    uint8_t target[6] = {};
    assert(mailbox.target(target) && target[0] == 2 && target[5] == 1);
    assert(AICNativeJoinRequestValid(delivered));
    assert(delivered.sequence == sequence && delivered.pmk[0] == 0xa5);
    assert(memcmp(delivered.stationMac, stationMac, 6) == 0);
    assert(!mailbox.take(&delivered, 102)); // Secret cannot be read twice.
    assert(!mailbox.finish(sequence + 1, 103));
    assert(mailbox.finish(sequence, 103));
    assert(!mailbox.active());
    assert(!mailbox.target(target));
    assert(!mailbox.finish(sequence, 104));

    uint32_t second = 0;
    assert(mailbox.begin(join, stationMac, 200, &second) && second != sequence);
    uint32_t aborted = 0;
    assert(mailbox.abort(&aborted) && aborted == second);
    assert(!mailbox.take(&delivered, 201));
    assert(!mailbox.abort(nullptr));

    assert(mailbox.begin(join, stationMac, 300, &second));
    assert(!mailbox.expire(30299, nullptr));
    assert(mailbox.expire(30300, &aborted) && aborted == second);
    assert(!mailbox.take(&delivered, 30301));
    assert(mailbox.begin(join, stationMac, 400, &second));
    assert(!mailbox.take(&delivered, 30400));
    assert(mailbox.expire(30400, nullptr));

    join.ssidLength = 33;
    assert(!mailbox.begin(join, stationMac, 500, &second));
    join.ssidLength = 4;
    join.channelSpec = 0;
    assert(!mailbox.begin(join, stationMac, 500, &second));
    join.channelSpec = 44;
    join.bssid[0] = 3;
    assert(!mailbox.begin(join, stationMac, 500, &second));
    return 0;
}
