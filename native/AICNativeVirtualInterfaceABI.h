#ifndef AIC_NATIVE_VIRTUAL_INTERFACE_ABI_H
#define AIC_NATIVE_VIRTUAL_INTERFACE_ABI_H

// macOS 15's IO80211VirtualInterface derives from the Skywalk interface, not
// directly from IOService as the older public reverse-engineered header says.
// Keep the exact local BootKC vtable tail here.  The opaque declarations use
// their real linker names so a concrete hardware subclass inherits Apple's
// implementations without relying on stale C++ signatures.

#include <Airport/macOS15/IO80211SkywalkInterface.h>

class IO80211VirtualInterface : public IO80211SkywalkInterface {
    OSDeclareAbstractStructors(IO80211VirtualInterface)

public:
    virtual void free() override;
    virtual IOReturn configureReport(IOReportChannelList*, unsigned int,
                                     void*, void*) override;
    virtual IOReturn updateReport(IOReportChannelList*, unsigned int,
                                  void*, void*) override;
    virtual bool start(IOService*) override;
    virtual void stop(IOService*) override;
    virtual bool terminate(IOOptionBits = 0) override;
    virtual bool attach(IOService*) override;
    virtual void detach(IOService*) override;
    virtual IOReturn newUserClient(task*, void*, unsigned int,
                                   OSDictionary*, IOUserClient**) override;
    virtual const char* stringFromReturn(int) override;
    virtual IOReturn enable(unsigned int) override;
    virtual IOReturn prepareBSDInterface(struct __ifnet*,
                                         unsigned int) override;
    virtual IOReturn processBSDCommand(struct __ifnet*, unsigned int,
                                       void*) override;
    virtual SInt32 setInterfaceEnable(bool) override;
    virtual UInt32 getFeatureFlags() override;
    virtual bool bpfTap(unsigned int, unsigned int) override;
    virtual bool setMulticastAddresses(ether_addr const*,
                                       unsigned int) override;
    virtual void* createPeerManager() override;
    virtual void postMessage(unsigned int, void*, unsigned long,
                             bool) override;
    virtual void logTxPacket(IO80211NetworkPacket*, PacketSkywalkScratch*,
                             apple80211_wme_ac, bool) override;
    virtual void logTxCompletionPacket(IO80211NetworkPacket*,
                                       PacketSkywalkScratch*, unsigned char*,
                                       apple80211_wme_ac, int, unsigned int,
                                       bool, bool) override;
    virtual IOReturn inputPacket(IO80211NetworkPacket*, packet_info_tag*,
                                 ether_header*, bool*, bool) override;
    virtual void logSkywalkTxReqPacket(IO80211NetworkPacket*,
                                       PacketSkywalkScratch*, unsigned char*,
                                       apple80211_wme_ac, bool) override;
    virtual SInt64 pendingPackets(unsigned char) override;
    virtual SInt64 packetSpace(unsigned char) override;
    virtual IO80211LinkState linkState() override;
    virtual void setScanningState(unsigned int, bool,
                                  apple80211_scan_data*, int) override;
    virtual void updateLinkParameters(
        apple80211_interface_availability*) override;
    virtual void updateInterfaceCoexRiskPct(unsigned long long) override;
    virtual void setInterfaceNF(apple80211_channel, long long) override;
    virtual void setDebugFlags(unsigned long long, unsigned int) override;
    virtual SInt64 debugFlags() override;
    virtual void setInterfaceChipCounters(
        apple80211_stat_report*, apple80211_chip_counters_tx*,
        apple80211_chip_error_counters_tx*,
        apple80211_chip_counters_rx*) override;
    virtual void setInterfaceMIBdot11(
        apple80211_stat_report*,
        apple80211_ManagementInformationBasedot11_counters*) override;
    virtual void setFrameStats(apple80211_stat_report*,
                               apple80211_frame_counters*) override;
    virtual void setInfraSpecificFrameStats(
        apple80211_stat_report*,
        apple80211_infra_specific_stats*) override;
    virtual SInt64 getWmeTxCounters(unsigned long long*) override;
    virtual void setWoWEnabled(bool) override;
    virtual bool wowEnabled() override;
    virtual void printDataPath(userPrintCtx*) override;
private:
    virtual void _abi_0c68() override
        __asm__("__ZN23IO80211VirtualInterface21findOrCreateFlowQueueE20IO80211FlowQueueHash");
    virtual void _abi_0c70() override
        __asm__("__ZN23IO80211VirtualInterface30findOrCreateFlowQueueWithCacheE20IO80211FlowQueueHashPb");
    virtual void _abi_0c78() override
        __asm__("__ZN23IO80211VirtualInterface21findExistingFlowQueueE20IO80211FlowQueueHash");
    virtual void _abi_0c80() override
        __asm__("__ZN23IO80211VirtualInterface17removePacketQueueEPK20IO80211FlowQueueHash");
public:
    virtual void flushPacketQueues() override;
    virtual void cachePeer(ether_addr*, unsigned int*) override;
    virtual bool shouldLog(unsigned long long) override;
    virtual void vlogDebug(unsigned long long, char const*, va_list) override;
    virtual void vlogDebugBPF(unsigned long long, char const*, va_list) override;
    virtual void* getP2PSkywalkPeerMgr() override;
private:
    virtual void _abi_0cd0() override
        __asm__("__ZN23IO80211VirtualInterface8findPeerER10ether_addr");
public:
    virtual int getEventPipeSize() override;
    virtual UInt64 createEventPipe(IO80211APIUserClient*) override;

private:
    virtual void _aic_abi_00() __asm__("__ZN23IO80211VirtualInterface4initEP17IO80211ControllerP10ether_addrjPKc");
    virtual void _aic_abi_01() __asm__("__ZN23IO80211VirtualInterface12setLinkStateE16IO80211LinkStatej");
    virtual void _aic_abi_02() __asm__("__ZN23IO80211VirtualInterface13forwardPacketEP20IO80211NetworkPacket");
    virtual void _aic_abi_03() __asm__("__ZN23IO80211VirtualInterface11handleIoctlEP7__ifnetmPv");
    virtual void _aic_abi_04() __asm__("__ZN23IO80211VirtualInterface14addPeerToCacheEPh");
    virtual void _aic_abi_05() __asm__("__ZN23IO80211VirtualInterface19deletePeerFromCacheEPh");
    virtual void _aic_abi_06() __asm__("__ZN23IO80211VirtualInterface14handleDebugCmdEP24apple80211_debug_command");
    virtual void _aic_abi_07() __asm__("__ZN23IO80211VirtualInterface20getPeerSlotDataStatsEP10ether_addrbP17peerSlotDataStats");
    virtual void _aic_abi_08() __asm__("__ZN23IO80211VirtualInterface16getPeerDataStatsEP10ether_addrbP16packetCounters_t");
    virtual void _aic_abi_09() __asm__("__ZN23IO80211VirtualInterface18clearPeerDataStatsEP10ether_addrb");
    virtual void _aic_abi_10() __asm__("__ZN23IO80211VirtualInterface34setAwdlCurrentChannelSequenceIndexEj");
    virtual void _aic_abi_11() __asm__("__ZN23IO80211VirtualInterface22isOutputFlowControlledEv");
    virtual void _aic_abi_12() __asm__("__ZN23IO80211VirtualInterface23setOutputFlowControlledEv");
    virtual void _aic_abi_13() __asm__("__ZN23IO80211VirtualInterface25clearOutputFlowControlledEv");
    virtual void _aic_abi_14() __asm__("__ZN23IO80211VirtualInterface18configureAQMOutputEv");
    virtual void _aic_abi_15() __asm__("__ZN23IO80211VirtualInterface11attachToBpfEv");
    virtual void _aic_abi_16() __asm__("__ZN23IO80211VirtualInterface14configureIfnetEv");
    virtual void _aic_abi_17() __asm__("__ZN23IO80211VirtualInterface5resetEv");
    virtual void _aic_abi_18() __asm__("__ZN23IO80211VirtualInterface25dupAndTransmitMcastPacketEP20IO80211NetworkPacketPhS2_");
    virtual void _aic_abi_19() __asm__("__ZN23IO80211VirtualInterface19freeMulticastPacketEP20IO80211NetworkPacket");
    virtual void _aic_abi_20() __asm__("__ZN23IO80211VirtualInterface22triggerAWDLMulticastTxEjh");
    virtual void _aic_abi_21() __asm__("__ZN23IO80211VirtualInterface14p2pMulticastTxEPP20IO80211NetworkPacketj");
    virtual void _aic_abi_22() __asm__("__ZN23IO80211VirtualInterface25sendPendingPacketsToStackEPP20IO80211NetworkPacketj");
    virtual void _aic_abi_23() __asm__("__ZN23IO80211VirtualInterface18freePendingPacketsEPP20IO80211NetworkPacketj");
    virtual void _aic_abi_24() __asm__("__ZN23IO80211VirtualInterface33_RESERVEDIO80211VirtualInterface0Ev");
    virtual void _aic_abi_25() __asm__("__ZN23IO80211VirtualInterface33_RESERVEDIO80211VirtualInterface1Ev");
    virtual void _aic_abi_26() __asm__("__ZN23IO80211VirtualInterface33_RESERVEDIO80211VirtualInterface2Ev");
    virtual void _aic_abi_27() __asm__("__ZN23IO80211VirtualInterface33_RESERVEDIO80211VirtualInterface3Ev");
    virtual void _aic_abi_28() __asm__("__ZN23IO80211VirtualInterface33_RESERVEDIO80211VirtualInterface4Ev");
    virtual void _aic_abi_29() __asm__("__ZN23IO80211VirtualInterface33_RESERVEDIO80211VirtualInterface5Ev");
    virtual void _aic_abi_30() __asm__("__ZN23IO80211VirtualInterface33_RESERVEDIO80211VirtualInterface6Ev");
    virtual void _aic_abi_31() __asm__("__ZN23IO80211VirtualInterface33_RESERVEDIO80211VirtualInterface7Ev");
    virtual void _aic_abi_32() __asm__("__ZN23IO80211VirtualInterface33_RESERVEDIO80211VirtualInterface8Ev");
    virtual void _aic_abi_33() __asm__("__ZN23IO80211VirtualInterface33_RESERVEDIO80211VirtualInterface9Ev");
    virtual void _aic_abi_34() __asm__("__ZN23IO80211VirtualInterface34_RESERVEDIO80211VirtualInterface10Ev");
    virtual void _aic_abi_35() __asm__("__ZN23IO80211VirtualInterface34_RESERVEDIO80211VirtualInterface11Ev");
    virtual void _aic_abi_36() __asm__("__ZN23IO80211VirtualInterface34_RESERVEDIO80211VirtualInterface12Ev");
    virtual void _aic_abi_37() __asm__("__ZN23IO80211VirtualInterface34_RESERVEDIO80211VirtualInterface13Ev");
    virtual void _aic_abi_38() __asm__("__ZN23IO80211VirtualInterface34_RESERVEDIO80211VirtualInterface14Ev");
    virtual void _aic_abi_39() __asm__("__ZN23IO80211VirtualInterface34_RESERVEDIO80211VirtualInterface15Ev");

    uint8_t _layout[0x120 - sizeof(IO80211SkywalkInterface)];
};

static_assert(sizeof(IO80211VirtualInterface) == 0x120,
              "macOS 15 IO80211VirtualInterface ABI size changed");

#endif
