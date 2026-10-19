#pragma once

#include <IO80211ControllerV2.h>
#include <macOS15/IO80211InfraProtocol.h>

// Offline-only WCL protocol interface. All WCL operations fail closed until
// their radio/service transport exists; there is no registration or AWDL yet.
class AICInfraInterface final : public IO80211InfraProtocol {
    OSDeclareDefaultStructors(AICInfraInterface)

public:
    bool initForAIC(IOService *provider, const uint8_t *mac);
    IOReturn getHardwareAddress(ether_addr *address) override;
    IOReturn setMacAddress(ether_addr &address) override;
    IOReturn setWCL_SCAN_REQ(apple80211ScanRequest *request) override;

#include "AICInfraProtocolStubs.inc"

private:
    ether_addr stationMac = {};
};
