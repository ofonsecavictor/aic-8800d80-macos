#pragma once

#include <IO80211ControllerV2.h>
#include <macOS15/IO80211InfraProtocol.h>

// Offline-only WCL protocol interface. Scan and WPA2 join handoffs are compiled
// only in the never-packaged native variant; no radio connection is proven.
class AICInfraInterface final : public IO80211InfraProtocol {
    OSDeclareDefaultStructors(AICInfraInterface)

public:
    bool initForAIC(IOService *provider, const uint8_t *mac);
    IOReturn getHardwareAddress(ether_addr *address) override;
    IOReturn setMacAddress(ether_addr &address) override;
    IOReturn getCHANNEL(apple80211_channel_data *data) override;
    IOReturn getOP_MODE(apple80211_opmode_data *data) override;
    IOReturn getRSSI(apple80211_rssi_data *data) override;
    IOReturn getHW_ADDR(apple80211_hw_mac_address *data) override;
    IOReturn setWCL_SCAN_REQ(apple80211ScanRequest *request) override;
    IOReturn setWCL_SCAN_ABORT(void *request) override;
    IOReturn setWCL_ASSOCIATE(apple80211AssocCandidates *request) override;
    IOReturn setWCL_JOIN_ABORT(void *request) override;
    IOReturn setWCL_LEAVE_NETWORK(
        apple80211_leave_network *request) override;
    IOReturn setWCL_LINK_STATE_UPDATE(
        apple80211_wcl_update_link_state *request) override;

#include "AICInfraProtocolStubs.inc"

private:
    ether_addr stationMac = {};
    IOService *radioProvider = nullptr;
};
