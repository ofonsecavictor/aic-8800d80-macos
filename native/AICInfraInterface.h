#pragma once

#include <IO80211ControllerV2.h>
#include <macOS15/IO80211InfraInterface.h>

// Offline-only IO80211 interface type. No registration, data path or AWDL yet.
class AICInfraInterface final : public IO80211InfraInterface {
    OSDeclareDefaultStructors(AICInfraInterface)

public:
    bool initForAIC(IOService *provider, const uint8_t *mac);
    IOReturn getHardwareAddress(ether_addr *address) override;
    IOReturn setMacAddress(ether_addr &address) override;

private:
    ether_addr stationMac = {};
};
