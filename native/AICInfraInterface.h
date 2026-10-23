#pragma once

#include <IO80211ControllerV2.h>
#include <macOS15/IO80211InfraProtocol.h>

// Offline-only WCL protocol interface. Scan and WPA2 join handoffs are compiled
// only in the never-packaged native variant; no radio connection is proven.
class AICInfraInterface final : public IO80211InfraProtocol {
    OSDeclareDefaultStructors(AICInfraInterface)

public:
    bool initForAIC(IOService *provider, const uint8_t *mac);
    IOReturn setPowerState(unsigned long state, IOService *provider) override;
    IOReturn getHardwareAddress(ether_addr *address) override;
    IOReturn setMacAddress(ether_addr &address) override;
    IOReturn getCHANNEL(apple80211_channel_data *data) override;
    IOReturn getOP_MODE(apple80211_opmode_data *data) override;
    IOReturn getRSSI(apple80211_rssi_data *data) override;
    IOReturn getHW_ADDR(apple80211_hw_mac_address *data) override;
    IOReturn getWCL_LOW_LATENCY_INFO(
        apple80211_low_latency_info *data) override;
    IOReturn getWCL_BSS_INFO(apple80211_beacon_msg *data) override;
    IOReturn getBEACON_INFO(apple80211_beacon_info_t *data) override;
    IOReturn getWCL_EXTENDED_BSS_INFO(
        apple80211_extended_bss_info *data) override;
    IOReturn getSUPPORTED_CHANNELS(apple80211_sup_channel_data *data) override;
    IOReturn getHW_SUPPORTED_CHANNELS(apple80211_sup_channel_data *data) override;
    IOReturn getCHANNELS_INFO(apple80211_channels_info *data) override;
    IOReturn getWCL_CHANNELS_INFO(apple80211ChannelInfo *data) override;
    IOReturn setWCL_SCAN_REQ(apple80211ScanRequest *request) override;
    IOReturn setWCL_SCAN_ABORT(void *request) override;
    IOReturn setWCL_ASSOCIATE(apple80211AssocCandidates *request) override;
    IOReturn setWCL_JOIN_ABORT(void *request) override;
    IOReturn setWCL_LEAVE_NETWORK(
        apple80211_leave_network *request) override;
    IOReturn setWCL_LINK_STATE_UPDATE(
        apple80211_wcl_update_link_state *request) override;
    IOReturn setWCL_UPDATE_FAST_LANE(apple80211_fastlane *request) override;

#include "AICInfraProtocolStubs.inc"

private:
    ether_addr stationMac = {};
    IOService *radioProvider = nullptr;
};
