// Compile-only AIC IO80211Controller ABI experiment for macOS 15.
// The default temporary Info.plist has a disabled match. The experimental
// USB-matched variant has loaded its provider, but not registered a controller:
// CoreCapture initialization, concurrent teardown, scan/join callbacks and
// the bidirectional data path are still unverified. The stable USB service
// retains ownership of the dongle.

#include <IO80211ControllerV2.h>
// The pinned macOS 15 controller header already includes the Skywalk packet
// types. The legacy include pulled by IO80211VirtualInterface.h redeclares
// TxPacketRequest, so suppress only that redundant header while retaining the
// full virtual-interface ABI declaration.
struct apple80211_pmk_cache_data;
struct packet_info_tx;
#define _IO80211INTERFACE_H
#include <IO80211VirtualInterface.h>
#undef _IO80211INTERFACE_H
#include <Airport/macOS15/FaultReporter.h>
#include <IOKit/IOLocks.h>
#include <IOKit/IOCommandGate.h>
#include <IOKit/IOTimerEventSource.h>
#include <IOKit/network/IOOutputQueue.h>
#include <IOKit/network/IOEthernetInterface.h>
#include <IOKit/network/IONetworkMedium.h>
#include <kern/clock.h>
#include <libkern/version.h>
#include <libkern/c++/OSNumber.h>
#include <libkern/c++/OSString.h>
#include <mach/kmod.h>
#include <net/if.h>
#include <net/kpi_interface.h>
#include <sys/kpi_mbuf.h>
#include "AICNativeBridgeProtocol.h"
#include "AICNativePowerMailbox.h"
#include "AICNativeFrameMailbox.h"
#include "AICNativeCapabilityBits.h"
#include "AICNativeStartupPolicy.h"
#include "AICNativeVirtualInterfacePolicy.h"
#include "AICNativeAWDLMailbox.h"
#include "AICNativeActionFrame.h"
#include "AICNativeBridgeUserClient.h"
#include "AICNativeEthernetInterface.h"
#include "AICSkywalkQueueABI.h"
#include "AICNativeScanWire.h"
#include "AICNativeJoinMailbox.h"
#include "AICNativeLeaveMailbox.h"
#include "AICWCLConnectionEvent.h"
#include "AICWCLBssCache.h"

class AICNativeUSBProvider final : public IOService {
    OSDeclareDefaultStructors(AICNativeUSBProvider)

public:
    bool start(IOService *provider) override;
    void free() override;
    IOWorkLoop *getWorkLoop() const override { return queue; }
    IO80211WorkQueue *nativeQueue() const { return queue; }

private:
    IO80211WorkQueue *queue = nullptr;
};

OSDefineMetaClassAndStructors(AICNativeUSBProvider, IOService)

static bool AICVerifiedUSBInterface(IOService *provider) {
    if (!provider) return false;
    OSNumber *vendor = OSDynamicCast(OSNumber, provider->getProperty("idVendor"));
    OSNumber *product = OSDynamicCast(OSNumber, provider->getProperty("idProduct"));
    OSNumber *index = OSDynamicCast(OSNumber, provider->getProperty("bInterfaceNumber"));
    OSNumber *interfaceClass = OSDynamicCast(
        OSNumber, provider->getProperty("bInterfaceClass"));
    OSNumber *configuration = OSDynamicCast(
        OSNumber, provider->getProperty("bConfigurationValue"));
    OSString *serial = OSDynamicCast(
        OSString, provider->getProperty("USB Serial Number"));
    return vendor && vendor->unsigned32BitValue() == 0xa69c &&
           product && product->unsigned32BitValue() == 0x8d81 &&
           index && index->unsigned32BitValue() == 2 &&
           interfaceClass && interfaceClass->unsigned32BitValue() == 255 &&
           configuration && configuration->unsigned32BitValue() == 1 &&
           serial && serial->isEqualTo("20220103");
}

bool AICNativeUSBProvider::start(IOService *provider) {
    if (version_major != 24 || version_minor < 2 ||
        !AICVerifiedUSBInterface(provider) ||
        !IOService::start(provider)) return false;
    queue = IO80211WorkQueue::workQueue();
    if (!queue) {
        IOLog("AICNative: provider work queue unavailable\n");
        IOService::stop(provider);
        return false;
    }
    IOLog("AICNative: provider ready, queue=%p\n", queue);
    registerService();
    return true;
}

extern "C" IO80211WorkQueue *AICDefaultWorkQueue()
    __asm__("__ZN16IO80211WorkQueue19getDefaultWorkQueueEv");
extern "C" void AICSetDefaultWorkQueue(IO80211WorkQueue *)
    __asm__("__ZN16IO80211WorkQueue19setDefaultWorkQueueEPS_");
extern "C" bool AICVirtualInterfaceInit(
    IO80211VirtualInterface *, IO80211Controller *, ether_addr *,
    unsigned int, const char *)
    __asm__("__ZN23IO80211VirtualInterface4initEP17IO80211ControllerP10ether_addrjPKc");
extern "C" void AICVirtualInterfaceSetEnabled(
    IO80211VirtualInterface *, bool)
    __asm__("__ZN23IO80211VirtualInterface18setInterfaceEnableEb");
extern "C" void AICVirtualInterfaceSetLinkState(
    IO80211VirtualInterface *, IO80211LinkState, unsigned int)
    __asm__("__ZN23IO80211VirtualInterface12setLinkStateE16IO80211LinkStatej");
extern "C" void AICVirtualInterfacePostMessage(
    IO80211VirtualInterface *, unsigned int, void *, unsigned long, bool)
    __asm__("__ZN23IO80211VirtualInterface11postMessageEjPvmb");

void AICNativeUSBProvider::free() {
    if (queue && AICDefaultWorkQueue() == queue)
        AICSetDefaultWorkQueue(nullptr);
    OSSafeReleaseNULL(queue);
    IOService::free();
}

class AICAirPortController final : public IO80211Controller {
    OSDeclareDefaultStructors(AICAirPortController)

public:
    bool init(OSDictionary *dictionary = nullptr) override;
    void free() override;
    IOWorkLoop *getWorkLoop() const override { return queue; }
    IO80211WorkQueue *getWorkQueue() const override { return queue; }
    bool createWorkLoop() override { return queue != nullptr; }
    bool createWorkQueue() override { return queue != nullptr; }
    bool start(IOService *provider) override;
    void stop(IOService *provider) override;
    IONetworkInterface *createInterface() override;
    SInt32 enableVirtualInterface(IO80211VirtualInterface *interface) override;
    SInt32 disableVirtualInterface(IO80211VirtualInterface *interface) override;
    IO80211VirtualInterface *createVirtualInterface(
        ether_addr *address, unsigned int role) override;
    int bpfOutputPacket(OSObject *object, unsigned int dataLinkType,
                        mbuf_t packet) override;
    bool isCommandProhibited(int command) override;
    IOReturn getHardwareAddress(IOEthernetAddress *address) override;
    SInt32 handleCardSpecific(IO80211SkywalkInterface *interface,
                             unsigned long command, void *data,
                             bool isSet) override;
    IOReturn getDRIVER_VERSION(IO80211SkywalkInterface *interface,
                               apple80211_version_data *data) override;
    IOReturn getHARDWARE_VERSION(IO80211SkywalkInterface *interface,
                                 apple80211_version_data *data) override;
    IOReturn getCARD_CAPABILITIES(IO80211SkywalkInterface *interface,
                                  apple80211_capability_data *data) override;
    IOReturn getPOWER(IO80211SkywalkInterface *interface,
                      apple80211_power_data *data) override;
    IOReturn setPOWER(IO80211SkywalkInterface *interface,
                      apple80211_power_data *data) override;
    IOReturn getCOUNTRY_CODE(IO80211SkywalkInterface *interface,
                             apple80211_country_code_data *data) override;
    IOReturn setCOUNTRY_CODE(IO80211SkywalkInterface *interface,
                             apple80211_country_code_data *data) override;
    IOReturn setGET_DEBUG_INFO(IO80211SkywalkInterface *interface,
                                apple80211_debug_command *data) override;
    CCLogStream *getLogger() const override;
    bool getLogPipes(CCPipe **logPipe, CCPipe **eventPipe,
                     CCPipe **snapshotsPipe) override;
    CommonFaultReporter *getFaultReporterFromDriver() override;
    IOReturn newUserClient(task_t owningTask, void *securityID, UInt32 type,
                           OSDictionary *properties,
                           IOUserClient **handler) override;
    IOReturn publishRadioState(const AICNativeRadioState &state);
    IOReturn setStationMac(const uint8_t mac[6]);
    IOReturn copyRadioState(AICNativeRadioState *state);
    IOReturn copyAssociatedBss(void *reply, size_t capacity);
    IOReturn copyAssociatedBeacon(void *reply, size_t capacity);
    IOReturn nextCommand(AICNativeCommand *command);
    IOReturn submitReceivedFrame(const AICNativeFrame &frame);
    IOReturn submitReceivedFrames(const AICNativeFrameBatch &batch);
    IOReturn nextReceivedFrame(AICNativeFrame *frame);
    IOReturn queueTransmitFrame(const AICNativeFrame &frame);
    IOReturn nextTransmitFrame(AICNativeFrame *frame);
    IOReturn nextTransmitFrames(AICNativeFrameBatch *batch);
    IOReturn beginScan(const AICWCLScanRequest &request);
    IOReturn abortScan();
    IOReturn nextScanRequest(AICNativeScanRequest *request);
    IOReturn submitScanResult(const AICNativeScanResult &result);
    IOReturn completeScan(const AICNativeScanCompletion &completion);
    IOReturn setScanBridgeEnabled(IOUserClient *client, bool enabled);
    IOReturn beginJoin(const AICWCLJoinRequest &request);
    IOReturn abortJoin();
    IOReturn nextJoinRequest(IOUserClient *client,
                             AICNativeJoinRequest *request);
    IOReturn completeJoin(IOUserClient *client,
                          const AICNativeJoinCompletion &completion);
    IOReturn requestLeave();
    IOReturn nextLeaveCommand(IOUserClient *client, AICNativeCommand *command);
    IOReturn nextAWDLState(AICNativeAWDLState *state);
    UInt32 outputPacket(mbuf_t packet, void *parameter) override;

private:
    bool initCoreCapture();
    void releaseCoreCapture();
#if defined(AIC_NATIVE_INTERFACE_PROBE) && AIC_NATIVE_INTERFACE_PROBE
    bool attachNativeInterface();
    void detachNativeInterface();
    bool createSkywalkQueues();
    void releaseSkywalkQueues();
    static IOReturn attachNativeGated(OSObject *owner, void *, void *, void *, void *);
    static IOReturn updateLinkGated(OSObject *owner, void *, void *, void *, void *);
    static IOReturn scanGated(OSObject *owner, void *operation,
                             void *payload, void *, void *);
    static void scanTimerFired(OSObject *owner, IOTimerEventSource *sender);
    static IOReturn joinGated(OSObject *owner, void *operation,
                             void *payload, void *client, void *);
    static void joinTimerFired(OSObject *owner, IOTimerEventSource *sender);
#endif
    IO80211WorkQueue *queue = nullptr;
    CCPipe *logPipe = nullptr;
    CCPipe *eventPipe = nullptr;
    CCPipe *snapshotsPipe = nullptr;
    CCLogStream *logger = nullptr;
    CCStream *faultStream = nullptr;
    CCFaultReporter *coreFaultReporter = nullptr;
    IO80211FaultReporter *faultReporter = nullptr;
    bool logPipeStarted = false;
    bool eventPipeStarted = false;
    bool snapshotsPipeStarted = false;
    IOCommandGate *commandGate = nullptr;
    IOTimerEventSource *scanTimer = nullptr;
    IOTimerEventSource *joinTimer = nullptr;
    AICInfraInterface *nativeInterface = nullptr;
    AICNativeEthernetInterface *bsdInterface = nullptr;
    IOSkywalkPacketBufferPool *skywalkPool = nullptr;
    IOSkywalkPacketQueue *skywalkQueues[4] = {};
    bool nativeAttached = false;
    bool controllerAttached = false;
    bool nativeStarted = false;
    IOLock *stateLock = nullptr;
    AICNativeRadioState radioState = {};
    bool stateReady = false;
    uint8_t requestedStationMac[6] = {};
    bool requestedStationMacReady = false;
    AICNativePowerMailbox powerMailbox;
    AICNativeFrameMailbox receivedFrames;
    AICNativeTransmitMailbox transmitFrames;
    AICNativeScanMailbox scanMailbox;
    AICWCLBssCache bssCache;
    AICNativeJoinMailbox joinMailbox;
    AICNativeLeaveMailbox leaveMailbox;
    AICNativeAWDLMailbox awdlMailbox;
    IO80211VirtualInterface *awdlInterface = nullptr;
    uint8_t awdlMac[6] = {};
    uint32_t awdlChannel = 0;
    bool awdlEnabled = false;
    bool scanBridgeEnabled = false;
    IOUserClient *scanOwner = nullptr; // Cleared by owner close or controller teardown.
    uint32_t transmitSequence = 0;
};

OSDefineMetaClassAndStructors(AICAirPortController, IO80211Controller)

#if defined(AIC_NATIVE_INTERFACE_PROBE) && AIC_NATIVE_INTERFACE_PROBE
// Sequoia's WCL does not treat scan messages as a live scan until the driver
// announces that its radio backend is available. Match the event layout used
// by the pinned AirportItlwm reference; never announce availability before
// the USB-owning scan bridge has published a powered radio.
struct AICWCLDriverAvailability {
    uint32_t version;
    uint32_t reserved0;
    uint32_t available;
    uint32_t reserved1;
    uint32_t reason;
    uint32_t subReason;
    uint8_t reserved2[0xf8 - 24];
};
static_assert(sizeof(AICWCLDriverAvailability) == 0xf8,
              "WCL driver availability event size");
#endif

bool AICAirPortController::init(OSDictionary *dictionary) {
    queue = AICDefaultWorkQueue();
    IOLog("AICNative: controller init, default queue=%p\n", queue);
    if (!queue) return false;
    queue->retain();
    if (!IO80211Controller::init(dictionary)) {
        IOLog("AICNative: controller base init failed\n");
        OSSafeReleaseNULL(queue);
        return false;
    }
    stateLock = IOLockAlloc();
    IOLog("AICNative: controller init complete, lock=%p\n", stateLock);
    if (!stateLock) OSSafeReleaseNULL(queue);
    return stateLock != nullptr;
}

void AICAirPortController::free() {
#if defined(AIC_NATIVE_INTERFACE_PROBE) && AIC_NATIVE_INTERFACE_PROBE
    detachNativeInterface();
#endif
    releaseCoreCapture();
    if (commandGate) {
        if (queue && commandGate->getWorkLoop())
            queue->removeEventSource(commandGate);
        OSSafeReleaseNULL(commandGate);
    }
    if (scanTimer) {
        scanTimer->cancelTimeout();
        if (queue && scanTimer->getWorkLoop())
            queue->removeEventSource(scanTimer);
        OSSafeReleaseNULL(scanTimer);
    }
    if (joinTimer) {
        joinTimer->cancelTimeout();
        if (queue && joinTimer->getWorkLoop())
            queue->removeEventSource(joinTimer);
        OSSafeReleaseNULL(joinTimer);
    }
    if (stateLock) {
        IOLockLock(stateLock);
        receivedFrames.clear();
        transmitFrames.clear();
        awdlMailbox.clear();
        IO80211VirtualInterface *awdl = awdlInterface;
        awdlInterface = nullptr;
        awdlEnabled = false;
        awdlChannel = 0;
        bzero(awdlMac, sizeof(awdlMac));
        bzero(&radioState, sizeof(radioState));
        IOLockUnlock(stateLock);
        if (awdl) awdl->release();
        IOLockFree(stateLock);
        stateLock = nullptr;
    }
    OSSafeReleaseNULL(queue);
    IO80211Controller::free();
}

bool AICAirPortController::start(IOService *provider) {
    // Only the test-EFI variant enables this path. Never publish a network
    // interface until the provider, shared work queue, and base start succeed.
#if defined(AIC_HEADLESS_BRIDGE_PROBE) && AIC_HEADLESS_BRIDGE_PROBE
    AICNativeUSBProvider *wrapper = OSDynamicCast(AICNativeUSBProvider, provider);
    if (version_major != 24 || version_minor < 2 || !wrapper ||
        !AICVerifiedUSBInterface(wrapper->getProvider())) {
        IOLog("AICNative: controller start rejected provider\n");
        return false;
    }
    if (!AICNativeSharedWorkLoop(static_cast<IOWorkLoop *>(queue),
                                 wrapper->getWorkLoop())) {
        IOLog("AICNative: controller/provider queue mismatch\n");
        return false;
    }
    IOLog("AICNative: controller start, shared queue=%p\n", queue);
#if defined(AIC_NATIVE_INTERFACE_PROBE) && AIC_NATIVE_INTERFACE_PROBE
    commandGate = IOCommandGate::commandGate(this);
    if (!commandGate || queue->addEventSource(commandGate) != kIOReturnSuccess) {
        IOLog("AICNative: controller command gate failed\n");
        return false;
    }
    scanTimer = IOTimerEventSource::timerEventSource(
        kIOTimerEventSourceOptionsPriorityWorkLoop, this, scanTimerFired);
    if (!scanTimer || queue->addEventSource(scanTimer) != kIOReturnSuccess) {
        IOLog("AICNative: controller scan timer failed\n");
        return false;
    }
    joinTimer = IOTimerEventSource::timerEventSource(
        kIOTimerEventSourceOptionsPriorityWorkLoop, this, joinTimerFired);
    if (!joinTimer || queue->addEventSource(joinTimer) != kIOReturnSuccess) {
        IOLog("AICNative: controller join timer failed\n");
        return false;
    }
#endif
    if (!initCoreCapture()) {
        IOLog("AICNative: CoreCapture setup failed\n");
        releaseCoreCapture();
        return false;
    }
    if (!IO80211Controller::start(provider)) {
        IOLog("AICNative: controller base start failed\n");
        releaseCoreCapture();
        return false;
    }
    IOLog("AICNative: controller base start complete\n");
    registerService();
    return true;
#else
    // Refuse to register a ghost Wi-Fi interface without an AIC radio bridge.
    (void)provider;
    return false;
#endif
}

void AICAirPortController::stop(IOService *provider) {
    // The IO80211 family must stop its controller while the registered
    // Skywalk interface and BSD child are still intact. A direct call to the
    // child interface's stop() from our detach path caused a page fault in
    // IO80211SkywalkInterface::stop on USB teardown.
    IO80211Controller::stop(provider);
#if defined(AIC_NATIVE_INTERFACE_PROBE) && AIC_NATIVE_INTERFACE_PROBE
    detachNativeInterface();
#endif
    if (stateLock) {
        IOLockLock(stateLock);
        receivedFrames.clear();
        transmitFrames.clear();
        stateReady = false;
        bzero(&radioState, sizeof(radioState));
        IOLockUnlock(stateLock);
    }
    // Power-management callbacks can outlive stop() on the Skywalk child.
    // Keep its logger and pipes alive until free(), after IOKit has released
    // the controller, so a delayed setPowerState() cannot log through a
    // stopped CoreCapture stream.
}

IONetworkInterface *AICAirPortController::createInterface() {
#if defined(AIC_NATIVE_INTERFACE_PROBE) && AIC_NATIVE_INTERFACE_PROBE
    if (!nativeInterface || !commandGate) return nullptr;
    auto *interface = OSTypeAlloc(AICNativeEthernetInterface);
    if (!interface) return nullptr;
    if (!interface->initForAIC(this, nativeInterface, commandGate)) {
        interface->release();
        return nullptr;
    }
    return interface;
#else
    return nullptr;
#endif
}

SInt32 AICAirPortController::enableVirtualInterface(
    IO80211VirtualInterface *interface) {
    if (!interface || interface->getProperty("AICNativeAWDL") != kOSBooleanTrue)
        return kIOReturnUnsupported;
    if (!stateLock) return kIOReturnNotReady;
    IOLockLock(stateLock);
    const bool ready = stateReady && radioState.powered;
    const uint32_t channel = radioState.channel ? radioState.channel : 6;
    const bool owned = awdlInterface == interface;
    IOLockUnlock(stateLock);
    if (!ready || !owned) return kIOReturnNotReady;
    const SInt32 status = IO80211Controller::enableVirtualInterface(interface);
    if (status != kIOReturnSuccess) return status;
    IOLockLock(stateLock);
    const bool published = awdlInterface == interface &&
        awdlMailbox.publish(awdlMac, true, channel);
    if (published) {
        awdlEnabled = true;
        awdlChannel = channel;
    }
    IOLockUnlock(stateLock);
    if (!published) {
        IO80211Controller::disableVirtualInterface(interface);
        return kIOReturnNotReady;
    }
    AICVirtualInterfaceSetEnabled(interface, true);
    AICVirtualInterfaceSetLinkState(interface, kIO80211NetworkLinkUp, 0);
    AICVirtualInterfacePostMessage(
        interface, APPLE80211_M_LINK_CHANGED, nullptr, 0, true);
    IOLog("AICNative: AWDL virtual interface enabled\n");
    return kIOReturnSuccess;
}

SInt32 AICAirPortController::disableVirtualInterface(
    IO80211VirtualInterface *interface) {
    if (!interface || interface->getProperty("AICNativeAWDL") != kOSBooleanTrue)
        return kIOReturnUnsupported;
    if (!stateLock) return kIOReturnNotReady;
    IOLockLock(stateLock);
    const bool owned = awdlInterface == interface;
    IOLockUnlock(stateLock);
    if (!owned) return kIOReturnNotReady;
    const SInt32 status = IO80211Controller::disableVirtualInterface(interface);
    if (status != kIOReturnSuccess) return status;
    IOLockLock(stateLock);
    const bool published = awdlInterface == interface &&
        awdlMailbox.publish(awdlMac, false, awdlChannel);
    if (published) awdlEnabled = false;
    IOLockUnlock(stateLock);
    if (!published) return kIOReturnNotReady;
    AICVirtualInterfaceSetLinkState(interface, kIO80211NetworkLinkDown, 0);
    AICVirtualInterfaceSetEnabled(interface, false);
    AICVirtualInterfacePostMessage(
        interface, APPLE80211_M_LINK_CHANGED, nullptr, 0, true);
    IOLog("AICNative: AWDL virtual interface disabled\n");
    return kIOReturnSuccess;
}

IO80211VirtualInterface *AICAirPortController::createVirtualInterface(
    ether_addr *address, unsigned int role) {
    static_assert(APPLE80211_VIF_AWDL == kAICVirtualInterfaceRoleAWDL,
                  "macOS 15 AWDL virtual-interface role changed");
    if (!address || !AICSupportsVirtualInterface(
            role, reinterpret_cast<const uint8_t *>(address),
            sizeof(*address))) {
        IOLog("AICNative: rejected virtual interface role=%u\n", role);
        return nullptr;
    }
    auto *interface = OSTypeAlloc(IO80211VirtualInterface);
    if (!interface) return nullptr;
    if (!AICVirtualInterfaceInit(interface, this, address, role,
                                 AICVirtualInterfacePrefix(role))) {
        interface->release();
        return nullptr;
    }
    if (!interface->setProperty("AICNativeAWDL", kOSBooleanTrue)) {
        interface->release();
        return nullptr;
    }
    if (!stateLock) {
        interface->release();
        return nullptr;
    }
    interface->retain();
    IOLockLock(stateLock);
    IO80211VirtualInterface *previous = awdlInterface;
    awdlInterface = interface;
    bcopy(address, awdlMac, sizeof(awdlMac));
    awdlEnabled = false;
    awdlChannel = radioState.channel;
    const bool published = awdlMailbox.publish(awdlMac, false, awdlChannel);
    IOLockUnlock(stateLock);
    if (previous) previous->release();
    if (!published) {
        IOLockLock(stateLock);
        awdlInterface = nullptr;
        bzero(awdlMac, sizeof(awdlMac));
        IOLockUnlock(stateLock);
        interface->release(); // Controller retain.
        interface->release(); // Allocation returned on failure.
        return nullptr;
    }
    IOLog("AICNative: created AWDL virtual interface\n");
    return interface;
}

int AICAirPortController::bpfOutputPacket(OSObject *object,
                                          unsigned int dataLinkType,
                                          mbuf_t packet) {
    if (!packet) return 1;
    const size_t length = (mbuf_flags(packet) & MBUF_PKTHDR)
        ? mbuf_pkthdr_len(packet) : mbuf_len(packet);
    uint8_t payload[512] = {};
    uint8_t source[6] = {};
    uint32_t channel = 0;
    uint32_t sequence = 0;
    bool ready = false;
    if (stateLock && dataLinkType == DLT_RAW && length <= sizeof(payload) &&
        mbuf_copydata(packet, 0, length, payload) == 0) {
        IOLockLock(stateLock);
        ready = awdlEnabled && awdlInterface == object && awdlChannel != 0;
        if (ready) {
            bcopy(awdlMac, source, sizeof(source));
            channel = awdlChannel;
            if (++transmitSequence == 0) ++transmitSequence;
            sequence = transmitSequence;
        }
        IOLockUnlock(stateLock);
    }
    AICNativeFrame frame = {};
    const bool accepted = ready && AICPrepareActionTransmit(
        &frame, payload, length, sequence, 1, channel, source) &&
        queueTransmitFrame(frame) == kIOReturnSuccess;
    mbuf_freem(packet);
    return accepted ? 0 : 1;
}

#if defined(AIC_NATIVE_INTERFACE_PROBE) && AIC_NATIVE_INTERFACE_PROBE
static UInt32 AICSkywalkTxSubmitUnimplemented(
    OSObject *, IOSkywalkPacketQueue *, IOSkywalkPacket *const *, UInt32 count,
    void *) {
    // Registration research only: consuming a packet without delivering it
    // to the radio would falsely report a working native data path.
    static volatile UInt32 calls = 0;
    if (__sync_fetch_and_add(&calls, 1) < 8)
        IOLog("AICNative: Skywalk TX submission invoked, packets=%u\n", count);
    return 0;
}

static UInt32 AICSkywalkRxSubmitUnimplemented(
    OSObject *, IOSkywalkPacketQueue *, IOSkywalkPacket *const *, UInt32 count,
    void *) {
    static volatile UInt32 calls = 0;
    if (__sync_fetch_and_add(&calls, 1) < 8)
        IOLog("AICNative: Skywalk RX submission invoked, packets=%u\n", count);
    return 0;
}

static UInt32 AICSkywalkCompleteUnimplemented(
    OSObject *, IOSkywalkPacketQueue *, IOSkywalkPacket **, UInt32,
    void *) {
    return 0;
}

bool AICAirPortController::createSkywalkQueues() {
    if (!nativeInterface || skywalkPool) return false;
    IOSkywalkPacketBufferPool::PoolOptions options = {};
    options.packetCount = 64;
    options.bufferCount = 64;
    options.bufferSize = 2048;
    options.maxBuffersPerPacket = 1;
    skywalkPool = IOSkywalkPacketBufferPool::withName(
        "AICNativeSTA", nativeInterface, 1, &options);
    if (!skywalkPool) return false;
    skywalkQueues[0] = AICCreateTxSubmissionQueue(
        skywalkPool, 64, 0, nativeInterface,
        AICSkywalkTxSubmitUnimplemented, nullptr, 0);
    skywalkQueues[1] = AICCreateTxCompletionQueue(
        skywalkPool, 64, 0, nativeInterface,
        AICSkywalkCompleteUnimplemented, nullptr, 0);
    skywalkQueues[2] = AICCreateRxSubmissionQueue(
        skywalkPool, 64, 0, 0, nativeInterface,
        AICSkywalkRxSubmitUnimplemented, nullptr, 0);
    skywalkQueues[3] = AICCreateRxCompletionQueue(
        skywalkPool, 64, 0, nativeInterface,
        AICSkywalkCompleteUnimplemented, nullptr, 0);
    for (auto *entry : skywalkQueues) {
        if (!entry) {
            releaseSkywalkQueues();
            return false;
        }
    }
    return true;
}

void AICAirPortController::releaseSkywalkQueues() {
    for (auto &entry : skywalkQueues) OSSafeReleaseNULL(entry);
    OSSafeReleaseNULL(skywalkPool);
}

IOReturn AICAirPortController::attachNativeGated(
    OSObject *owner, void *, void *, void *, void *) {
    auto *controller = OSDynamicCast(AICAirPortController, owner);
    if (!controller || !controller->commandGate || !controller->queue ||
        !controller->queue->inGate()) return kIOReturnNotPermitted;
    return controller->attachNativeInterface() ? kIOReturnSuccess
                                                : kIOReturnNotReady;
}

IOReturn AICAirPortController::updateLinkGated(
    OSObject *owner, void *, void *, void *, void *) {
    auto *controller = OSDynamicCast(AICAirPortController, owner);
    if (!controller || !controller->queue || !controller->queue->inGate())
        return kIOReturnNotPermitted;
    if (!controller->nativeStarted || !controller->bsdInterface ||
        !controller->bsdInterface->getIfnet()) return kIOReturnNotReady;
    IOLockLock(controller->stateLock);
    const bool connected = controller->stateReady &&
        controller->radioState.powered && controller->radioState.associated;
    IOLockUnlock(controller->stateLock);
    controller->setLinkStatus(kIONetworkLinkValid |
        (connected ? kIONetworkLinkActive : 0));
    ifnet_t interface = controller->bsdInterface->getIfnet();
    if (interface) {
        const uint16_t flags = ifnet_flags(interface);
        ifnet_set_flags(interface,
                        connected ? flags | IFF_RUNNING : flags & ~IFF_RUNNING,
                        IFF_RUNNING);
    }
    if (!connected && controller->nativeInterface) {
        controller->nativeInterface->setCurrentApAddress(nullptr);
        controller->nativeInterface->setLinkState(
            kIO80211NetworkLinkDown, 0, false, 0);
    }
    return kIOReturnSuccess;
}

bool AICAirPortController::attachNativeInterface() {
    if (nativeInterface) return nativeStarted && bsdInterface;
    IOEthernetAddress address = {};
    if (!commandGate || !stateReady ||
        getHardwareAddress(&address) != kIOReturnSuccess) return false;
    OSDictionary *media = OSDictionary::withCapacity(1);
    if (!media) return false;
    IONetworkMedium *medium = IONetworkMedium::medium(kIOMediumIEEE80211, 54000000);
    if (!medium) {
        media->release();
        return false;
    }
    IONetworkMedium::addMedium(media, medium);
    const bool published = publishMediumDictionary(media);
    if (published) {
        setCurrentMedium(medium);
        setSelectedMedium(medium);
    }
    medium->release();
    media->release();
    if (!published) return false;

    nativeInterface = OSTypeAlloc(AICInfraInterface);
    if (!nativeInterface || !nativeInterface->initForAIC(
            this, reinterpret_cast<const uint8_t *>(&address))) {
        detachNativeInterface();
        return false;
    }
    nativeInterface->setInterfaceRole(1);
    nativeInterface->setInterfaceId(1);
    nativeAttached = nativeInterface->attach(this);
    if (!nativeAttached) {
        detachNativeInterface();
        return false;
    }
    controllerAttached = attachInterface(nativeInterface, this);
    if (!controllerAttached) {
        detachNativeInterface();
        return false;
    }
    IONetworkInterface *bsd = nullptr;
    if (!IONetworkController::attachInterface(&bsd, false)) {
        detachNativeInterface();
        return false;
    }
    auto *typedBSD = OSDynamicCast(AICNativeEthernetInterface, bsd);
    if (!typedBSD) {
        if (bsd) IONetworkController::detachInterface(bsd, true);
        detachNativeInterface();
        return false;
    }
    IOLockLock(stateLock);
    bsdInterface = typedBSD;
    IOLockUnlock(stateLock);
    IOSkywalkEthernetInterface::RegistrationInfo info = {};
    if (!nativeInterface->initRegistrationInfo(&info, 1, sizeof(info))) {
        detachNativeInterface();
        return false;
    }
    // These expansion-data pointers belong to IOSkywalkFamily. The former
    // IOMalloc assignments made teardown kfree_type() panic on macOS 15.
    // Do not populate them until registration uses the family's queue/pool
    // API, which allocates the matching typed objects itself.
    nativeInterface->deferBSDAttach(true);
    nativeStarted = nativeInterface->start(this);
    if (!nativeStarted) {
        detachNativeInterface();
        return false;
    }
    if (!createSkywalkQueues() ||
        AICRegisterSkywalkEthernet(nativeInterface, &info, skywalkQueues, 4,
                                   skywalkPool, skywalkPool, 0) !=
            kIOReturnSuccess) {
        detachNativeInterface();
        return false;
    }
    setLinkStatus(kIONetworkLinkValid);
    bsdInterface->registerService();
    return true;
}

void AICAirPortController::detachNativeInterface() {
    if (scanTimer) scanTimer->cancelTimeout();
    if (joinTimer) joinTimer->cancelTimeout();
    scanBridgeEnabled = false;
    scanOwner = nullptr;
    uint32_t aborted = 0;
    if (scanMailbox.abort(&aborted) && nativeInterface) {
        IOReturn status = kIOReturnAborted;
        postMessage(nativeInterface, 237, &status, sizeof(status), true);
    }
    uint8_t joinBSSID[6] = {};
    if (joinMailbox.target(joinBSSID) && joinMailbox.abort(nullptr) &&
        nativeInterface) {
        AICWCLConnectionEvent event = AICMakeWCLConnectionEvent(
            joinBSSID, false, kIOReturnAborted);
        postMessage(nativeInterface, 213, &event, sizeof(event), true);
    }
    leaveMailbox.clear();
    // Do not call nativeInterface->stop(this) explicitly. The family owns
    // that stop sequence; invoking it directly on an already registered
    // interface panicked at IO80211SkywalkInterface::stop+0xd5.
    if (stateLock) {
        IOLockLock(stateLock);
        AICNativeEthernetInterface *bsd = bsdInterface;
        bsdInterface = nullptr;
        IOLockUnlock(stateLock);
        if (bsd) IONetworkController::detachInterface(bsd, true);
    }
    if (nativeInterface) {
        if (controllerAttached) detachInterface(nativeInterface, true);
        if (nativeAttached) nativeInterface->detach(this);
        releaseSkywalkQueues();
        OSSafeReleaseNULL(nativeInterface);
    }
    nativeStarted = controllerAttached = nativeAttached = false;
}
#endif

#if defined(AIC_NATIVE_INTERFACE_PROBE) && AIC_NATIVE_INTERFACE_PROBE
static uint64_t AICNativeUptimeMillis() {
    uint64_t uptime = 0;
    uint64_t nanoseconds = 0;
    clock_get_uptime(&uptime);
    absolutetime_to_nanoseconds(uptime, &nanoseconds);
    return nanoseconds / 1000000;
}

void AICAirPortController::scanTimerFired(
    OSObject *owner, IOTimerEventSource *sender) {
    auto *self = OSDynamicCast(AICAirPortController, owner);
    if (!self || sender != self->scanTimer) return;
    uint32_t expired = 0;
    if (self->scanMailbox.expire(AICNativeUptimeMillis(), &expired)) {
        if (self->nativeInterface) {
            IOReturn status = kIOReturnTimeout;
            self->postMessage(self->nativeInterface, 237, &status,
                              sizeof(status), true);
        }
    } else {
        AICNativeScanTicket pending = {};
        if (self->scanMailbox.read(&pending))
            sender->setTimeoutMS(100);
    }
}

void AICAirPortController::joinTimerFired(
    OSObject *owner, IOTimerEventSource *sender) {
    auto *self = OSDynamicCast(AICAirPortController, owner);
    if (!self || sender != self->joinTimer) return;
    uint8_t bssid[6] = {};
    if (!self->joinMailbox.target(bssid) ||
        !self->joinMailbox.expire(AICNativeUptimeMillis(), nullptr)) return;
    self->leaveMailbox.request();
    if (self->nativeInterface) {
        AICWCLConnectionEvent event = AICMakeWCLConnectionEvent(
            bssid, false, kIOReturnTimeout);
        self->postMessage(self->nativeInterface, 213, &event, sizeof(event), true);
    }
}

enum AICJoinOperation {
    kAICJoinBegin = 1,
    kAICJoinAbort = 2,
    kAICJoinNext = 3,
    kAICJoinComplete = 4,
    kAICJoinLeave = 5,
    kAICJoinNextLeave = 6,
};

IOReturn AICAirPortController::joinGated(
    OSObject *owner, void *operation, void *payload, void *client, void *) {
    auto *self = OSDynamicCast(AICAirPortController, owner);
    if (!self || !self->queue || !self->queue->inGate())
        return kIOReturnNotPermitted;
    const auto op = static_cast<AICJoinOperation>(
        reinterpret_cast<uintptr_t>(operation));
    if (op == kAICJoinAbort) {
        if (self->joinTimer) self->joinTimer->cancelTimeout();
        uint8_t bssid[6] = {};
        const bool active = self->joinMailbox.target(bssid);
        self->joinMailbox.abort(nullptr);
        self->leaveMailbox.request();
        if (active && self->nativeInterface) {
            AICWCLConnectionEvent event = AICMakeWCLConnectionEvent(
                bssid, false, kIOReturnAborted);
            self->postMessage(self->nativeInterface, 213, &event,
                              sizeof(event), true);
        }
        if (self->nativeInterface)
            self->postMessage(self->nativeInterface, 214, nullptr, 0, true);
        return kIOReturnSuccess;
    }
    if (!self->nativeStarted || !self->nativeInterface ||
        !self->scanBridgeEnabled || !self->scanOwner ||
        !self->bsdInterface || !self->bsdInterface->getIfnet())
        return kIOReturnNotReady;
    if ((op == kAICJoinNext || op == kAICJoinComplete ||
         op == kAICJoinNextLeave) &&
        client != self->scanOwner) return kIOReturnNotPermitted;
    const uint64_t now = AICNativeUptimeMillis();
    if (op == kAICJoinLeave) {
        uint8_t bssid[6] = {};
        if (self->joinMailbox.target(bssid)) {
            self->joinMailbox.abort(nullptr);
            if (self->joinTimer) self->joinTimer->cancelTimeout();
            AICWCLConnectionEvent event = AICMakeWCLConnectionEvent(
                bssid, false, kIOReturnAborted);
            self->postMessage(self->nativeInterface, 213, &event,
                              sizeof(event), true);
        }
        self->leaveMailbox.request();
        return kIOReturnSuccess;
    }
    if (op == kAICJoinNextLeave)
        return payload && self->leaveMailbox.take(
            static_cast<AICNativeCommand *>(payload))
            ? kIOReturnSuccess : kIOReturnNotReady;
    if (op == kAICJoinBegin) {
        if (!payload || self->joinMailbox.active()) return kIOReturnBusy;
        AICNativeScanTicket scan = {};
        if (self->scanMailbox.read(&scan)) return kIOReturnBusy;
        uint8_t stationMac[6] = {};
        IOLockLock(self->stateLock);
        const bool ready = self->stateReady && self->radioState.powered &&
                           !self->radioState.associated;
        const bool macReady = self->requestedStationMacReady;
        if (macReady)
            bcopy(self->requestedStationMac, stationMac, sizeof(stationMac));
        IOLockUnlock(self->stateLock);
        if (!ready || !macReady)
            return kIOReturnNotReady;
        const auto *requested = static_cast<const AICWCLJoinRequest *>(payload);
        IOLockLock(self->stateLock);
        const bool bssReady = self->bssCache.select(requested->bssid);
        IOLockUnlock(self->stateLock);
        if (!bssReady) return kIOReturnNotReady;
        uint32_t sequence = 0;
        if (!self->joinMailbox.begin(
                *requested,
                stationMac, now,
                &sequence)) return kIOReturnBadArgument;
        if (!self->joinTimer || self->joinTimer->setTimeoutMS(
                AICNativeJoinMailbox::kTimeoutMillis) != kIOReturnSuccess) {
            self->joinMailbox.abort(nullptr);
            return kIOReturnNotReady;
        }
        return kIOReturnSuccess;
    }
    if (op == kAICJoinNext)
        return payload && self->joinMailbox.take(
            static_cast<AICNativeJoinRequest *>(payload), now)
            ? kIOReturnSuccess : kIOReturnNotReady;
    if (op == kAICJoinComplete) {
        if (!payload) return kIOReturnBadArgument;
        const auto &completion =
            *static_cast<const AICNativeJoinCompletion *>(payload);
        if (!AICNativeJoinCompletionValid(completion))
            return kIOReturnBadArgument;
        uint8_t bssid[6] = {};
        if (!self->joinMailbox.target(bssid)) return kIOReturnNotReady;
        if (!completion.status) {
            IOLockLock(self->stateLock);
            const bool associated = self->stateReady &&
                self->radioState.associated &&
                bcmp(self->radioState.bssid, bssid, 6) == 0;
            IOLockUnlock(self->stateLock);
            if (!associated) return kIOReturnNotReady;
        }
        if (!self->joinMailbox.finish(completion.sequence, now))
            return kIOReturnBadArgument;
        if (self->joinTimer) self->joinTimer->cancelTimeout();
        AICWCLConnectionEvent event = AICMakeWCLConnectionEvent(
            bssid, completion.status == 0,
            static_cast<int32_t>(completion.status));
        if (!completion.status) {
            AICWCLLinkStatusEvent link = AICMakeWCLLinkStatusEvent(bssid, true);
            IOReturn linked = self->postMessage(
                self->nativeInterface, 216, &link, sizeof(link), true);
            if (linked == kIOReturnSuccess) {
                // The successful WPA2 path selected this BSSID from a real
                // scan result. WCL needs FirstBeacon before ConnectComplete
                // to leave NET_MANAGER_STATE_LINK_DOWN on macOS 15.
                AICWCLFirstBeaconEvent beacon =
                    AICMakeWCLFirstBeaconEvent(bssid);
                linked = self->postMessage(
                    self->nativeInterface, 212, &beacon, sizeof(beacon), true);
            }
            if (linked != kIOReturnSuccess) {
                event = AICMakeWCLConnectionEvent(bssid, false, linked);
                self->leaveMailbox.request();
            }
        }
        return self->postMessage(self->nativeInterface, 213, &event,
                                 sizeof(event), true);
    }
    return kIOReturnUnsupported;
}

enum AICScanOperation {
    kAICScanBegin = 1,
    kAICScanAbort = 2,
    kAICScanNext = 3,
    kAICScanResult = 4,
    kAICScanComplete = 5,
    kAICScanEnable = 6,
    kAICScanDisable = 7,
};

IOReturn AICAirPortController::scanGated(
    OSObject *owner, void *operation, void *payload, void *, void *) {
    auto *self = OSDynamicCast(AICAirPortController, owner);
    if (!self || !self->queue || !self->queue->inGate())
        return kIOReturnNotPermitted;
    const auto op = static_cast<AICScanOperation>(
        reinterpret_cast<uintptr_t>(operation));
    const uint64_t now = AICNativeUptimeMillis();
    uint32_t expired = 0;
    if (self->scanMailbox.expire(now, &expired) && self->nativeInterface) {
        if (self->scanTimer) self->scanTimer->cancelTimeout();
        IOReturn status = kIOReturnTimeout;
        self->postMessage(self->nativeInterface, 237, &status,
                          sizeof(status), true);
    }
    if (op == kAICScanDisable || op == kAICScanAbort) {
        if (op == kAICScanDisable) {
            if (payload != self->scanOwner) return kIOReturnSuccess;
            self->scanBridgeEnabled = false;
            self->scanOwner = nullptr;
            AICWCLDriverAvailability unavailable = {};
            unavailable.version = 3;
            unavailable.reason = 0xe0821804;
            self->postMessage(self->nativeInterface, 55, &unavailable,
                              sizeof(unavailable), true);
            self->leaveMailbox.clear();
            // A crashed USB-owning process must not leave a ghost connected
            // interface or accept packets after its privileged client closes.
            IOLockLock(self->stateLock);
            if (self->stateReady) {
                self->radioState.powered = 0;
                self->radioState.associated = 0;
                self->radioState.channel = 0;
                self->radioState.rssi_dbm = 0;
                bzero(self->radioState.bssid, sizeof(self->radioState.bssid));
                self->powerMailbox.observe(false);
            }
            self->receivedFrames.clear();
            self->transmitFrames.clear();
            IOLockUnlock(self->stateLock);
            self->setLinkStatus(kIONetworkLinkValid);
            if (self->nativeInterface) {
                self->nativeInterface->setCurrentApAddress(nullptr);
                self->nativeInterface->setLinkState(
                    kIO80211NetworkLinkDown, 0, false, 0);
            }
            if (self->joinTimer) self->joinTimer->cancelTimeout();
            uint8_t bssid[6] = {};
            if (self->joinMailbox.target(bssid) &&
                self->joinMailbox.abort(nullptr) && self->nativeInterface) {
                AICWCLConnectionEvent event = AICMakeWCLConnectionEvent(
                    bssid, false, kIOReturnAborted);
                self->postMessage(self->nativeInterface, 213, &event,
                                  sizeof(event), true);
            }
        }
        if (self->scanTimer) self->scanTimer->cancelTimeout();
        uint32_t aborted = 0;
        if (self->scanMailbox.abort(&aborted) && self->nativeInterface) {
            IOReturn status = kIOReturnAborted;
            self->postMessage(self->nativeInterface, 237, &status,
                              sizeof(status), true);
        }
        return kIOReturnSuccess;
    }
    if (!self->nativeStarted || !self->nativeInterface ||
        !self->bsdInterface || !self->bsdInterface->getIfnet())
        return kIOReturnNotReady;
    if (op == kAICScanEnable) {
        if (!payload || (self->scanOwner && self->scanOwner != payload))
            return kIOReturnBusy;
        IOLockLock(self->stateLock);
        const bool powered = self->stateReady && self->radioState.powered;
        IOLockUnlock(self->stateLock);
        if (!powered) return kIOReturnNotReady;
        self->scanBridgeEnabled = true;
        self->scanOwner = static_cast<IOUserClient *>(payload);
        uint32_t reset = 1;
        self->postMessage(self->nativeInterface, 49, &reset,
                          sizeof(reset), true);
        AICWCLDriverAvailability available = {};
        available.version = 3;
        available.available = 1;
        available.reason = 0xe0821803;
        const IOReturn announced = self->postMessage(
            self->nativeInterface, 55, &available, sizeof(available), true);
        if (announced != kIOReturnSuccess) {
            self->scanBridgeEnabled = false;
            self->scanOwner = nullptr;
            return announced;
        }
        return kIOReturnSuccess;
    }
    if (!self->scanBridgeEnabled) return kIOReturnNotReady;
    if (op == kAICScanBegin) {
        if (!payload) return kIOReturnBadArgument;
        if (self->joinMailbox.active()) return kIOReturnBusy;
        IOLockLock(self->stateLock);
        const bool powered = self->stateReady && self->radioState.powered;
        IOLockUnlock(self->stateLock);
        if (!powered) return kIOReturnNotReady;
        AICNativeScanTicket ticket = {};
        if (!self->scanMailbox.begin(
                *static_cast<const AICWCLScanRequest *>(payload), now,
                &ticket)) return kIOReturnBusy;
        if (!self->scanTimer || self->scanTimer->setTimeoutMS(
                AICNativeScanMailbox::kTimeoutMillis) != kIOReturnSuccess) {
            self->scanMailbox.abort(nullptr);
            return kIOReturnNotReady;
        }
        return kIOReturnSuccess;
    }
    if (op == kAICScanNext) {
        if (!payload) return kIOReturnBadArgument;
        AICNativeScanTicket ticket = {};
        if (!self->scanMailbox.read(&ticket)) return kIOReturnNotReady;
        return AICEncodeNativeScanRequest(
            ticket, *static_cast<AICNativeScanRequest *>(payload))
            ? kIOReturnSuccess : kIOReturnError;
    }
    if (op == kAICScanResult) {
        if (!payload) return kIOReturnBadArgument;
        const auto &result = *static_cast<const AICNativeScanResult *>(payload);
        if (!AICNativeScanResultValid(result)) return kIOReturnBadArgument;
        if (!self->scanMailbox.acceptResult(result.sequence, result.data,
                                            result.length, now))
            return kIOReturnBadArgument;
        IOLockLock(self->stateLock);
        const bool cached = self->bssCache.remember(
            result.data, result.length, result.beacon,
            result.beaconLength);
        IOLockUnlock(self->stateLock);
        if (!cached) return kIOReturnBadArgument;
        return self->postMessage(self->nativeInterface, 201,
                                 const_cast<uint8_t *>(result.data),
                                 result.length, true);
    }
    if (op == kAICScanComplete) {
        if (!payload) return kIOReturnBadArgument;
        const auto &completion =
            *static_cast<const AICNativeScanCompletion *>(payload);
        if (!AICNativeScanCompletionValid(completion))
            return kIOReturnBadArgument;
        if (!self->scanMailbox.finish(completion.sequence, now))
            return kIOReturnBadArgument;
        if (self->scanTimer) self->scanTimer->cancelTimeout();
        IOReturn status = static_cast<IOReturn>(completion.status);
        return self->postMessage(self->nativeInterface, 237, &status,
                                 sizeof(status), true);
    }
    return kIOReturnUnsupported;
}
#endif

IOReturn AICAirPortController::beginScan(const AICWCLScanRequest &request) {
#if defined(AIC_NATIVE_INTERFACE_PROBE) && AIC_NATIVE_INTERFACE_PROBE
    return commandGate ? commandGate->runAction(
        scanGated, reinterpret_cast<void *>(uintptr_t(kAICScanBegin)),
        const_cast<AICWCLScanRequest *>(&request)) : kIOReturnNotReady;
#else
    (void)request;
    return kIOReturnUnsupported;
#endif
}

IOReturn AICAirPortController::abortScan() {
#if defined(AIC_NATIVE_INTERFACE_PROBE) && AIC_NATIVE_INTERFACE_PROBE
    return commandGate ? commandGate->runAction(
        scanGated, reinterpret_cast<void *>(uintptr_t(kAICScanAbort)))
        : kIOReturnNotReady;
#else
    return kIOReturnUnsupported;
#endif
}

IOReturn AICAirPortController::nextScanRequest(AICNativeScanRequest *request) {
    if (!request) return kIOReturnBadArgument;
#if defined(AIC_NATIVE_INTERFACE_PROBE) && AIC_NATIVE_INTERFACE_PROBE
    return commandGate ? commandGate->runAction(
        scanGated, reinterpret_cast<void *>(uintptr_t(kAICScanNext)), request)
        : kIOReturnNotReady;
#else
    return kIOReturnUnsupported;
#endif
}

IOReturn AICAirPortController::submitScanResult(
    const AICNativeScanResult &result) {
#if defined(AIC_NATIVE_INTERFACE_PROBE) && AIC_NATIVE_INTERFACE_PROBE
    return commandGate ? commandGate->runAction(
        scanGated, reinterpret_cast<void *>(uintptr_t(kAICScanResult)),
        const_cast<AICNativeScanResult *>(&result)) : kIOReturnNotReady;
#else
    (void)result;
    return kIOReturnUnsupported;
#endif
}

IOReturn AICAirPortController::completeScan(
    const AICNativeScanCompletion &completion) {
#if defined(AIC_NATIVE_INTERFACE_PROBE) && AIC_NATIVE_INTERFACE_PROBE
    return commandGate ? commandGate->runAction(
        scanGated, reinterpret_cast<void *>(uintptr_t(kAICScanComplete)),
        const_cast<AICNativeScanCompletion *>(&completion)) : kIOReturnNotReady;
#else
    (void)completion;
    return kIOReturnUnsupported;
#endif
}

IOReturn AICAirPortController::setScanBridgeEnabled(
    IOUserClient *client, bool enabled) {
#if defined(AIC_NATIVE_INTERFACE_PROBE) && AIC_NATIVE_INTERFACE_PROBE
    if (!client) return kIOReturnBadArgument;
    return commandGate ? commandGate->runAction(
        scanGated, reinterpret_cast<void *>(uintptr_t(
            enabled ? kAICScanEnable : kAICScanDisable)), client)
        : kIOReturnNotReady;
#else
    (void)client;
    (void)enabled;
    return kIOReturnUnsupported;
#endif
}

IOReturn AICAirPortController::beginJoin(const AICWCLJoinRequest &request) {
#if defined(AIC_NATIVE_INTERFACE_PROBE) && AIC_NATIVE_INTERFACE_PROBE
    return commandGate ? commandGate->runAction(
        joinGated, reinterpret_cast<void *>(uintptr_t(kAICJoinBegin)),
        const_cast<AICWCLJoinRequest *>(&request)) : kIOReturnNotReady;
#else
    (void)request;
    return kIOReturnUnsupported;
#endif
}

IOReturn AICAirPortController::abortJoin() {
#if defined(AIC_NATIVE_INTERFACE_PROBE) && AIC_NATIVE_INTERFACE_PROBE
    return commandGate ? commandGate->runAction(
        joinGated, reinterpret_cast<void *>(uintptr_t(kAICJoinAbort)))
        : kIOReturnNotReady;
#else
    return kIOReturnUnsupported;
#endif
}

IOReturn AICAirPortController::nextJoinRequest(
    IOUserClient *client, AICNativeJoinRequest *request) {
    if (!client || !request) return kIOReturnBadArgument;
#if defined(AIC_NATIVE_INTERFACE_PROBE) && AIC_NATIVE_INTERFACE_PROBE
    return commandGate ? commandGate->runAction(
        joinGated, reinterpret_cast<void *>(uintptr_t(kAICJoinNext)), request,
        client)
        : kIOReturnNotReady;
#else
    (void)client;
    return kIOReturnUnsupported;
#endif
}

IOReturn AICAirPortController::completeJoin(
    IOUserClient *client, const AICNativeJoinCompletion &completion) {
    if (!client) return kIOReturnBadArgument;
#if defined(AIC_NATIVE_INTERFACE_PROBE) && AIC_NATIVE_INTERFACE_PROBE
    return commandGate ? commandGate->runAction(
        joinGated, reinterpret_cast<void *>(uintptr_t(kAICJoinComplete)),
        const_cast<AICNativeJoinCompletion *>(&completion), client)
        : kIOReturnNotReady;
#else
    (void)client;
    (void)completion;
    return kIOReturnUnsupported;
#endif
}

IOReturn AICAirPortController::requestLeave() {
#if defined(AIC_NATIVE_INTERFACE_PROBE) && AIC_NATIVE_INTERFACE_PROBE
    return commandGate ? commandGate->runAction(
        joinGated, reinterpret_cast<void *>(uintptr_t(kAICJoinLeave)))
        : kIOReturnNotReady;
#else
    return kIOReturnUnsupported;
#endif
}

IOReturn AICAirPortController::nextLeaveCommand(
    IOUserClient *client, AICNativeCommand *command) {
    if (!client || !command) return kIOReturnBadArgument;
#if defined(AIC_NATIVE_INTERFACE_PROBE) && AIC_NATIVE_INTERFACE_PROBE
    return commandGate ? commandGate->runAction(
        joinGated, reinterpret_cast<void *>(uintptr_t(kAICJoinNextLeave)),
        command, client) : kIOReturnNotReady;
#else
    (void)client;
    return kIOReturnUnsupported;
#endif
}

bool AICAirPortController::isCommandProhibited(int) {
#if defined(AIC_NATIVE_INTERFACE_PROBE) && AIC_NATIVE_INTERFACE_PROBE
    return false;
#else
    return true;
#endif
}

IOReturn AICAirPortController::getHardwareAddress(IOEthernetAddress *address) {
    static_assert(sizeof(IOEthernetAddress) == 6, "Ethernet MAC ABI size");
    if (!address || !stateLock) return kIOReturnBadArgument;
    IOLockLock(stateLock);
    if (!stateReady) {
        IOLockUnlock(stateLock);
        return kIOReturnNotReady;
    }
    bcopy(radioState.mac, address, sizeof(*address));
    IOLockUnlock(stateLock);
    return kIOReturnSuccess;
}

SInt32 AICAirPortController::handleCardSpecific(
    IO80211SkywalkInterface *, unsigned long, void *, bool) {
    return kIOReturnUnsupported;
}

IOReturn AICAirPortController::getDRIVER_VERSION(
    IO80211SkywalkInterface *, apple80211_version_data *data) {
    if (!data) return kIOReturnBadArgument;
    static const char driverVersion[] = "AIC 8800D80 native 0.0.19-airdrop.2";
    static_assert(sizeof(driverVersion) <= sizeof(data->string), "driver version too long");
    bzero(data, sizeof(*data));
    data->version = APPLE80211_VERSION;
    bcopy(driverVersion, data->string, sizeof(driverVersion));
    data->string_len = sizeof(driverVersion) - 1;
    return kIOReturnSuccess;
}

IOReturn AICAirPortController::getHARDWARE_VERSION(
    IO80211SkywalkInterface *, apple80211_version_data *data) {
    if (!data) return kIOReturnBadArgument;
    static const char hardwareVersion[] = "AIC 8800D80 USB; firmware not reported";
    static_assert(sizeof(hardwareVersion) <= sizeof(data->string), "hardware version too long");
    bzero(data, sizeof(*data));
    data->version = APPLE80211_VERSION;
    bcopy(hardwareVersion, data->string, sizeof(hardwareVersion));
    data->string_len = sizeof(hardwareVersion) - 1;
    return kIOReturnSuccess;
}

IOReturn AICAirPortController::getCARD_CAPABILITIES(
    IO80211SkywalkInterface *, apple80211_capability_data *data) {
    if (!data) return kIOReturnBadArgument;
    // Capabilities belong to the controller, not the current USB owner.
    // airportd queries them before the userspace radio bridge has published
    // its first state; refusing that query can make en2 disappear from
    // CoreWLAN even though the IOService/BSD interface remains registered.
    bzero(data, sizeof(*data));
    data->version = APPLE80211_VERSION;
    // Only WPA2/CCMP has been exercised with this dongle. The legacy card
    // capability bitmap has no AWDL bit; AWDL is negotiated through a
    // separately-created virtual interface. Do not advertise WPA3, monitor,
    // or WEP. The scan bridge now delivers completion through WCL; without
    // this Sequoia capability bit, Apple80211Scan does
    // not monitor the completion event and discards the native scan.
    if (!AICSetNativeCapability(data->capabilities,
                                sizeof(data->capabilities),
                                APPLE80211_CAP_AES_CCM) ||
        !AICSetNativeCapability(data->capabilities,
                                sizeof(data->capabilities),
                                APPLE80211_CAP_WPA2))
        return kIOReturnError;
    data->capabilities[5] |= 0x40; // WCL scan-completion event support.
    return kIOReturnSuccess;
}

IOReturn AICAirPortController::getPOWER(
    IO80211SkywalkInterface *, apple80211_power_data *data) {
    if (!data || !stateLock) return kIOReturnBadArgument;
    IOLockLock(stateLock);
    // Before the bridge owns the USB radio, report OFF rather than refusing
    // the query. macOS must be able to discover and later power on en2.
    const bool powered = stateReady && radioState.powered != 0;
    IOLockUnlock(stateLock);
    bzero(data, sizeof(*data));
    data->version = APPLE80211_VERSION;
    data->num_radios = 1;
    data->power_state[0] = powered ? APPLE80211_POWER_ON : APPLE80211_POWER_OFF;
    return kIOReturnSuccess;
}

IOReturn AICAirPortController::publishRadioState(
    const AICNativeRadioState &state) {
    if (!stateLock || !AICNativeRadioStateValid(state)) return kIOReturnBadArgument;
    IOLockLock(stateLock);
    if (!requestedStationMacReady) {
        bcopy(state.mac, requestedStationMac, sizeof(requestedStationMac));
        requestedStationMacReady = true;
    }
    const bool linkChanged = stateReady &&
        (radioState.powered != state.powered ||
         radioState.associated != state.associated ||
         bcmp(radioState.bssid, state.bssid, 6) != 0 ||
         bcmp(radioState.mac, state.mac, 6) != 0);
    if (linkChanged || !state.powered) {
        receivedFrames.clear();
        transmitFrames.clear();
    }
    radioState = state;
    stateReady = true;
    powerMailbox.observe(state.powered != 0);
    IOLockUnlock(stateLock);
#if defined(AIC_NATIVE_INTERFACE_PROBE) && AIC_NATIVE_INTERFACE_PROBE
    if (commandGate && !nativeInterface)
        return commandGate->runAction(attachNativeGated);
    if (commandGate && (linkChanged || !state.powered))
        return commandGate->runAction(updateLinkGated);
#endif
    return kIOReturnSuccess;
}

IOReturn AICAirPortController::setStationMac(const uint8_t mac[6]) {
    if (!mac || !stateLock || (mac[0] & 1)) return kIOReturnBadArgument;
    bool nonzero = false;
    for (unsigned i = 0; i < 6; ++i) nonzero |= mac[i] != 0;
    if (!nonzero) return kIOReturnBadArgument;
    IOLockLock(stateLock);
    if (!stateReady || radioState.associated || !bsdInterface ||
        !bsdInterface->getIfnet()) {
        IOLockUnlock(stateLock);
        return kIOReturnNotReady;
    }
    AICNativeEthernetInterface *target = bsdInterface;
    target->retain();
    ifnet_t interface = target->getIfnet();
    const errno_t referenceStatus = ifnet_reference(interface);
    IOLockUnlock(stateLock);
    if (referenceStatus != 0) {
        target->release();
        return kIOReturnNotReady;
    }
    // WCL changes the station address without IOEthernetInterface's normal
    // MAC ioctl. DHCP/ARP use the BSD address, while the radio join uses the
    // requested address; both must be identical before association begins.
    const errno_t addressStatus = ifnet_set_lladdr(interface, mac, 6);
    if (addressStatus == 0) {
        target->setProperty(kIOMACAddress, const_cast<uint8_t *>(mac), 6);
        IOLockLock(stateLock);
        if (stateReady && !radioState.associated && bsdInterface == target) {
            bcopy(mac, requestedStationMac, sizeof(requestedStationMac));
            requestedStationMacReady = true;
        } else {
            IOLockUnlock(stateLock);
            ifnet_release(interface);
            target->release();
            return kIOReturnNotReady;
        }
        IOLockUnlock(stateLock);
    }
    ifnet_release(interface);
    target->release();
    if (addressStatus != 0) return kIOReturnError;
    return kIOReturnSuccess;
}

IOReturn AICAirPortController::copyRadioState(AICNativeRadioState *state) {
    if (!state || !stateLock) return kIOReturnBadArgument;
    IOLockLock(stateLock);
    if (!stateReady) {
        IOLockUnlock(stateLock);
        return kIOReturnNotReady;
    }
    *state = radioState;
    IOLockUnlock(stateLock);
    return kIOReturnSuccess;
}

IOReturn AICAirPortController::copyAssociatedBss(void *reply,
                                                size_t capacity) {
    if (!reply || capacity < AICWCLBssCache::kReplyCapacity || !stateLock)
        return kIOReturnBadArgument;
    IOLockLock(stateLock);
    // WCL may ask for BSS_INFO while the service is still publishing its
    // association state. The selected scan result is pinned by beginJoin and
    // remains valid through the synchronous LinkStatus callback.
    const bool ready = stateReady && bssCache.copySelected(reply, capacity);
    IOLockUnlock(stateLock);
    return ready ? kIOReturnSuccess : kIOReturnNotReady;
}

IOReturn AICAirPortController::copyAssociatedBeacon(void *reply,
                                                   size_t capacity) {
    if (!reply || capacity < AICWCLBssCache::kBeaconReplyCapacity || !stateLock)
        return kIOReturnBadArgument;
    IOLockLock(stateLock);
    const bool ready = stateReady &&
        bssCache.copySelectedBeacon(reply, capacity);
    IOLockUnlock(stateLock);
    return ready ? kIOReturnSuccess : kIOReturnNotReady;
}

IOReturn AICAirPortController::nextCommand(AICNativeCommand *command) {
    if (!command || !stateLock) return kIOReturnBadArgument;
    IOLockLock(stateLock);
    if (!powerMailbox.read(command)) {
        IOLockUnlock(stateLock);
        return kIOReturnNotReady;
    }
    IOLockUnlock(stateLock);
    return kIOReturnSuccess;
}

IOReturn AICAirPortController::nextAWDLState(AICNativeAWDLState *state) {
    if (!state || !stateLock) return kIOReturnBadArgument;
    IOLockLock(stateLock);
    const bool available = awdlMailbox.read(state);
    IOLockUnlock(stateLock);
    return available ? kIOReturnSuccess : kIOReturnNotReady;
}

IOReturn AICAirPortController::submitReceivedFrame(
    const AICNativeFrame &frame) {
    if (!stateLock || !AICNativeFrameValid(frame, true))
        return kIOReturnBadArgument;
    if (frame.kind == kAICNativeFrameEthernet) {
        // This stays unavailable until a future registration path binds a BSD
        // interface. Never acknowledge RX data into a ghost network service.
        IOLockLock(stateLock);
        const bool associated = stateReady && radioState.associated;
        const bool addressed = (frame.data[0] & 1) ||
            bcmp(frame.data, radioState.mac, 6) == 0;
        IOEthernetInterface *target = bsdInterface;
        if (target) target->retain();
        IOLockUnlock(stateLock);
        if (!associated || !target || !target->getIfnet()) {
            if (target) target->release();
            return kIOReturnNotReady;
        }
        if (!addressed) {
            target->release();
            return kIOReturnBadArgument;
        }
        mbuf_t packet = allocatePacket(frame.length);
        if (!packet) {
            target->release();
            return kIOReturnNoMemory;
        }
        if (mbuf_copyback(packet, 0, frame.length, frame.data,
                          MBUF_DONTWAIT) != 0) {
            freePacket(packet);
            target->release();
            return kIOReturnNoMemory;
        }
        target->inputPacket(packet, frame.length);
        target->release();
        return kIOReturnSuccess;
    }
    IO80211VirtualInterface *target = nullptr;
    IOLockLock(stateLock);
    if (awdlEnabled && awdlInterface) {
        target = awdlInterface;
        target->retain();
    }
    IOLockUnlock(stateLock);
    if (!target) return kIOReturnNotReady;
    // IO80211 copies the bounded action payload while posting the synchronous
    // message; peer data is never persisted by the driver.
    AICVirtualInterfacePostMessage(target, APPLE80211_M_ACTION_FRAME,
                                   const_cast<uint8_t *>(frame.data),
                                   frame.length, true);
    target->release();
    return kIOReturnSuccess;
}

IOReturn AICAirPortController::nextReceivedFrame(AICNativeFrame *frame) {
    if (!frame || !stateLock) return kIOReturnBadArgument;
    IOLockLock(stateLock);
    const bool available = receivedFrames.pop(frame);
    IOLockUnlock(stateLock);
    return available ? kIOReturnSuccess : kIOReturnNotReady;
}

IOReturn AICAirPortController::submitReceivedFrames(
    const AICNativeFrameBatch &batch) {
    if (!AICNativeFrameBatchValid(batch, true)) return kIOReturnBadArgument;
    // Frames are still delivered through the same validated ingress path;
    // batching removes user-client crossings without changing packet rules.
    for (uint32_t i = 0; i < batch.count; ++i) {
        const IOReturn status = submitReceivedFrame(batch.frames[i]);
        if (status != kIOReturnSuccess) return status;
    }
    return kIOReturnSuccess;
}

IOReturn AICAirPortController::queueTransmitFrame(
    const AICNativeFrame &frame) {
    if (!stateLock || !AICNativeFrameValid(frame, false))
        return kIOReturnBadArgument;
    IOLockLock(stateLock);
    const bool ready = stateReady && radioState.powered &&
        (frame.kind != kAICNativeFrameEthernet || radioState.associated);
    const bool queued = ready && transmitFrames.push(frame, false);
    IOLockUnlock(stateLock);
    return queued ? kIOReturnSuccess :
        (ready ? kIOReturnNoSpace : kIOReturnNotReady);
}

UInt32 AICAirPortController::outputPacket(mbuf_t packet, void *) {
    if (!packet) return kIOReturnOutputDropped;
    const bool hasHeader = (mbuf_flags(packet) & MBUF_PKTHDR) != 0;
    const size_t length = hasHeader ? mbuf_pkthdr_len(packet) : 0;
    AICNativeFrame frame = {};
    bool valid = stateLock && hasHeader &&
                 length >= 14 && length <= kAICNativeFrameMaxBytes;
    if (valid) {
        frame.version = kAICNativeBridgeVersion;
        frame.kind = kAICNativeFrameEthernet;
        frame.vif = 0;
        frame.length = static_cast<uint32_t>(length);
        IOLockLock(stateLock);
        if (++transmitSequence == 0) ++transmitSequence;
        frame.sequence = transmitSequence;
        IOLockUnlock(stateLock);
        if (mbuf_copydata(packet, 0, length, frame.data) == 0) {
            const IOReturn status = queueTransmitFrame(frame);
            valid = status == kIOReturnSuccess;
            if (status == kIOReturnNoSpace) {
                // Count only full-mailbox drops; print at powers of two so a
                // browser burst is measurable without logging packet data or
                // flooding the kernel log during a sustained backlog.
                static volatile uint32_t fullDrops = 0;
                const uint32_t count = __sync_add_and_fetch(&fullDrops, 1);
                if ((count & (count - 1)) == 0)
                    IOLog("AICNative: TX mailbox full, drops=%u\n", count);
            }
        }
    }
    freePacket(packet);
    return valid ? kIOReturnOutputSuccess : kIOReturnOutputDropped;
}

IOReturn AICAirPortController::nextTransmitFrame(AICNativeFrame *frame) {
    if (!frame || !stateLock) return kIOReturnBadArgument;
    IOLockLock(stateLock);
    const bool available = transmitFrames.pop(frame);
    IOLockUnlock(stateLock);
    return available ? kIOReturnSuccess : kIOReturnNotReady;
}

IOReturn AICAirPortController::nextTransmitFrames(AICNativeFrameBatch *batch) {
    if (!batch || !stateLock) return kIOReturnBadArgument;
    bzero(batch, sizeof(*batch));
    batch->version = kAICNativeBridgeVersion;
    IOLockLock(stateLock);
    while (batch->count < kAICNativeFrameBatchCapacity &&
           transmitFrames.pop(&batch->frames[batch->count])) {
        ++batch->count;
    }
    IOLockUnlock(stateLock);
    return batch->count ? kIOReturnSuccess : kIOReturnNotReady;
}

extern "C" IOReturn AICNativePublishState(
    IOService *service, const AICNativeRadioState *state) {
    if (!service || !state) return kIOReturnBadArgument;
    AICAirPortController *controller = OSDynamicCast(AICAirPortController, service);
    if (!controller) return kIOReturnBadArgument;
    return controller->publishRadioState(*state);
}

extern "C" IOReturn AICNativeCopyRadioState(
    IOService *service, AICNativeRadioState *state) {
    if (!service || !state) return kIOReturnBadArgument;
    AICAirPortController *controller = OSDynamicCast(AICAirPortController, service);
    if (!controller) return kIOReturnBadArgument;
    return controller->copyRadioState(state);
}

extern "C" IOReturn AICNativeCopyAssociatedBss(
    IOService *service, void *reply, size_t capacity) {
    auto *controller = OSDynamicCast(AICAirPortController, service);
    return controller ? controller->copyAssociatedBss(reply, capacity)
                      : kIOReturnBadArgument;
}

extern "C" IOReturn AICNativeCopyAssociatedBeacon(
    IOService *service, void *reply, size_t capacity) {
    auto *controller = OSDynamicCast(AICAirPortController, service);
    return controller ? controller->copyAssociatedBeacon(reply, capacity)
                      : kIOReturnBadArgument;
}

extern "C" IOReturn AICNativeSetStationMac(
    IOService *service, const uint8_t mac[6]) {
    auto *controller = OSDynamicCast(AICAirPortController, service);
    return controller ? controller->setStationMac(mac) : kIOReturnBadArgument;
}

extern "C" IOReturn AICNativeNextCommand(
    IOService *service, AICNativeCommand *command) {
    if (!service || !command) return kIOReturnBadArgument;
    AICAirPortController *controller = OSDynamicCast(AICAirPortController, service);
    if (!controller) return kIOReturnBadArgument;
    return controller->nextCommand(command);
}

extern "C" IOReturn AICNativeNextAWDLState(
    IOService *service, AICNativeAWDLState *state) {
    if (!service || !state) return kIOReturnBadArgument;
    auto *controller = OSDynamicCast(AICAirPortController, service);
    return controller ? controller->nextAWDLState(state)
                      : kIOReturnBadArgument;
}

extern "C" IOReturn AICNativeBeginScan(
    IOService *service, const AICWCLScanRequest *request) {
    if (!service || !request) return kIOReturnBadArgument;
    auto *controller = OSDynamicCast(AICAirPortController, service);
    return controller ? controller->beginScan(*request) : kIOReturnBadArgument;
}

extern "C" IOReturn AICNativeAbortScan(IOService *service) {
    auto *controller = OSDynamicCast(AICAirPortController, service);
    return controller ? controller->abortScan() : kIOReturnBadArgument;
}

extern "C" IOReturn AICNativeNextScanRequest(
    IOService *service, AICNativeScanRequest *request) {
    auto *controller = OSDynamicCast(AICAirPortController, service);
    return controller ? controller->nextScanRequest(request) : kIOReturnBadArgument;
}

extern "C" IOReturn AICNativeSubmitScanResult(
    IOService *service, const AICNativeScanResult *result) {
    if (!result) return kIOReturnBadArgument;
    auto *controller = OSDynamicCast(AICAirPortController, service);
    return controller ? controller->submitScanResult(*result)
                      : kIOReturnBadArgument;
}

extern "C" IOReturn AICNativeCompleteScan(
    IOService *service, const AICNativeScanCompletion *completion) {
    if (!completion) return kIOReturnBadArgument;
    auto *controller = OSDynamicCast(AICAirPortController, service);
    return controller ? controller->completeScan(*completion)
                      : kIOReturnBadArgument;
}

extern "C" IOReturn AICNativeSetScanBridgeEnabled(
    IOService *service, IOUserClient *client, bool enabled) {
    auto *controller = OSDynamicCast(AICAirPortController, service);
    return controller ? controller->setScanBridgeEnabled(client, enabled)
                      : kIOReturnBadArgument;
}

extern "C" IOReturn AICNativeBeginJoin(
    IOService *service, const AICWCLJoinRequest *request) {
    if (!request) return kIOReturnBadArgument;
    auto *controller = OSDynamicCast(AICAirPortController, service);
    return controller ? controller->beginJoin(*request) : kIOReturnBadArgument;
}

extern "C" IOReturn AICNativeAbortJoin(IOService *service) {
    auto *controller = OSDynamicCast(AICAirPortController, service);
    return controller ? controller->abortJoin() : kIOReturnBadArgument;
}

extern "C" IOReturn AICNativeNextJoinRequest(
    IOService *service, IOUserClient *client, AICNativeJoinRequest *request) {
    auto *controller = OSDynamicCast(AICAirPortController, service);
    return controller ? controller->nextJoinRequest(client, request)
                      : kIOReturnBadArgument;
}

extern "C" IOReturn AICNativeCompleteJoin(
    IOService *service, IOUserClient *client,
    const AICNativeJoinCompletion *completion) {
    if (!completion) return kIOReturnBadArgument;
    auto *controller = OSDynamicCast(AICAirPortController, service);
    return controller ? controller->completeJoin(client, *completion)
                      : kIOReturnBadArgument;
}

extern "C" IOReturn AICNativeRequestLeave(IOService *service) {
    auto *controller = OSDynamicCast(AICAirPortController, service);
    return controller ? controller->requestLeave() : kIOReturnBadArgument;
}

extern "C" IOReturn AICNativeNextLeaveCommand(
    IOService *service, IOUserClient *client, AICNativeCommand *command) {
    auto *controller = OSDynamicCast(AICAirPortController, service);
    return controller ? controller->nextLeaveCommand(client, command)
                      : kIOReturnBadArgument;
}

extern "C" IOReturn AICNativeSubmitReceivedFrame(
    IOService *service, const AICNativeFrame *frame) {
    if (!service || !frame) return kIOReturnBadArgument;
    AICAirPortController *controller = OSDynamicCast(AICAirPortController, service);
    if (!controller) return kIOReturnBadArgument;
    return controller->submitReceivedFrame(*frame);
}

extern "C" IOReturn AICNativeSubmitReceivedFrames(
    IOService *service, const AICNativeFrameBatch *batch) {
    if (!service || !batch) return kIOReturnBadArgument;
    auto *controller = OSDynamicCast(AICAirPortController, service);
    return controller ? controller->submitReceivedFrames(*batch)
                      : kIOReturnBadArgument;
}

extern "C" IOReturn AICNativeNextTransmitFrame(
    IOService *service, AICNativeFrame *frame) {
    if (!service || !frame) return kIOReturnBadArgument;
    AICAirPortController *controller = OSDynamicCast(AICAirPortController, service);
    if (!controller) return kIOReturnBadArgument;
    return controller->nextTransmitFrame(frame);
}

extern "C" IOReturn AICNativeNextTransmitFrames(
    IOService *service, AICNativeFrameBatch *batch) {
    if (!service || !batch) return kIOReturnBadArgument;
    auto *controller = OSDynamicCast(AICAirPortController, service);
    return controller ? controller->nextTransmitFrames(batch)
                      : kIOReturnBadArgument;
}

// These are the controller-side handoff points for a future IO80211 data path.
// The current Infra interface does not call them or register with macOS.
extern "C" IOReturn AICNativeNextReceivedFrame(
    IOService *service, AICNativeFrame *frame) {
    if (!service || !frame) return kIOReturnBadArgument;
    AICAirPortController *controller = OSDynamicCast(AICAirPortController, service);
    if (!controller) return kIOReturnBadArgument;
    return controller->nextReceivedFrame(frame);
}

extern "C" IOReturn AICNativeQueueTransmitFrame(
    IOService *service, const AICNativeFrame *frame) {
    if (!service || !frame) return kIOReturnBadArgument;
    AICAirPortController *controller = OSDynamicCast(AICAirPortController, service);
    if (!controller) return kIOReturnBadArgument;
    return controller->queueTransmitFrame(*frame);
}

IOReturn AICAirPortController::setPOWER(
    IO80211SkywalkInterface *, apple80211_power_data *data) {
    if (!data || !stateLock || data->version != APPLE80211_VERSION ||
        data->num_radios == 0 || data->power_state[0] > APPLE80211_POWER_ON) {
        return kIOReturnBadArgument;
    }
    const uint32_t requested = data->power_state[0] == APPLE80211_POWER_ON;
    IOLockLock(stateLock);
    powerMailbox.request(requested, stateReady, radioState.powered != 0);
    IOLockUnlock(stateLock);
    return kIOReturnSuccess;
}

IOReturn AICAirPortController::getCOUNTRY_CODE(
    IO80211SkywalkInterface *, apple80211_country_code_data *data) {
    if (!data) return kIOReturnBadArgument;
    bzero(data, sizeof(*data));
    data->version = APPLE80211_VERSION;
    // Unknown/world domain for passive scan research only. This is not a
    // claim that the dongle is certified for transmission in any country.
    data->cc[0] = 'X';
    data->cc[1] = '0';
    return kIOReturnSuccess;
}

IOReturn AICAirPortController::setCOUNTRY_CODE(
    IO80211SkywalkInterface *, apple80211_country_code_data *) {
    return kIOReturnUnsupported;
}

IOReturn AICAirPortController::setGET_DEBUG_INFO(
    IO80211SkywalkInterface *, apple80211_debug_command *) {
    return kIOReturnUnsupported;
}

bool AICAirPortController::initCoreCapture() {
    if (!queue || logPipe || eventPipe || snapshotsPipe) return false;

    CCPipeOptions options = {};
    options.pipe_size = 0x200000;
    options.min_log_size_notify = 0xccccc;
    options.notify_threshold = 1000;
    options.log_data_type = 1;
    options.pad9 = 0x1000000;
    options.pad10 = 2;
    strlcpy(options.file_name, "AIC_Driver_Logs", sizeof(options.file_name));
    strlcpy(options.name, "wlan0", sizeof(options.name));
    strlcpy(options.directory_name, "WiFi", sizeof(options.directory_name));
    logPipe = CCPipe::withOwnerNameCapacity(
        this, "local.victor.AICNativeProbe", "DriverLogs", &options);
    if (!logPipe || !(logPipeStarted = logPipe->CCPipe::startPipe()))
        return false;
    CCStreamOptions streamOptions = {};
    CCStream *stream = CCStream::withPipeAndName(
        logPipe, "AICNative", &streamOptions);
    logger = OSDynamicCast(CCLogStream, stream);
    if (!logger) {
        OSSafeReleaseNULL(stream);
        return false;
    }

    bzero(&options, sizeof(options));
    options.pipe_size = 0x200000;
    options.min_log_size_notify = 0xccccc;
    options.notify_threshold = 1000;
    options.pad9 = 0x2;
    options.pad10 = 0x2800000;
    strlcpy(options.file_name, "AIC_Datapath", sizeof(options.file_name));
    strlcpy(options.directory_name, "WiFi", sizeof(options.directory_name));
    eventPipe = CCPipe::withOwnerNameCapacity(
        this, "local.victor.AICNativeProbe", "DatapathEvents", &options);
    if (!eventPipe || !(eventPipeStarted = eventPipe->CCPipe::startPipe()))
        return false;

    bzero(&options, sizeof(options));
    options.pipe_type = 0x200000001ULL;
    options.log_data_type = 2;
    options.pipe_size = 128;
    strlcpy(options.file_name, "AIC_State_Snapshots", sizeof(options.file_name));
    strlcpy(options.name, "0", sizeof(options.name));
    strlcpy(options.directory_name, "WiFi", sizeof(options.directory_name));
    snapshotsPipe = CCPipe::withOwnerNameCapacity(
        this, "local.victor.AICNativeProbe", "StateSnapshots", &options);
    if (!snapshotsPipe ||
        !(snapshotsPipeStarted = snapshotsPipe->CCPipe::startPipe()))
        return false;

    bzero(&streamOptions, sizeof(streamOptions));
    streamOptions.stream_type = 1;
    streamOptions.console_level = ~0ULL;
    faultStream = CCStream::withPipeAndName(
        snapshotsPipe, "FaultReporter", &streamOptions);
    CCDataStream *data = OSDynamicCast(CCDataStream, faultStream);
    if (!data) return false;
    coreFaultReporter = CCFaultReporter::withStreamWorkloop(data, queue);
    if (!coreFaultReporter) return false;
    faultReporter = IO80211FaultReporter::allocWithParams(coreFaultReporter);
    return faultReporter != nullptr;
}

void AICAirPortController::releaseCoreCapture() {
    OSSafeReleaseNULL(faultReporter);
    OSSafeReleaseNULL(coreFaultReporter);
    OSSafeReleaseNULL(faultStream);
    OSSafeReleaseNULL(logger);
    if (snapshotsPipeStarted) {
        snapshotsPipe->CCPipe::stopPipe();
        snapshotsPipeStarted = false;
    }
    if (eventPipeStarted) {
        eventPipe->CCPipe::stopPipe();
        eventPipeStarted = false;
    }
    if (logPipeStarted) {
        logPipe->CCPipe::stopPipe();
        logPipeStarted = false;
    }
    OSSafeReleaseNULL(snapshotsPipe);
    OSSafeReleaseNULL(eventPipe);
    OSSafeReleaseNULL(logPipe);
}

CCLogStream *AICAirPortController::getLogger() const {
    return logger;
}

bool AICAirPortController::getLogPipes(
    CCPipe **log, CCPipe **event, CCPipe **snapshots) {
    if (log) *log = logPipe;
    if (event) *event = eventPipe;
    if (snapshots) *snapshots = snapshotsPipe;
    return logPipe && eventPipe && snapshotsPipe;
}

CommonFaultReporter *AICAirPortController::getFaultReporterFromDriver() {
    return faultReporter;
}

IOReturn AICAirPortController::newUserClient(
    task_t owningTask, void *securityID, UInt32 type,
    OSDictionary *properties, IOUserClient **handler) {
    if (!handler || type != 0) return kIOReturnBadArgument;
    *handler = nullptr;
    if (IOUserClient::clientHasPrivilege(
            securityID, kIOClientPrivilegeAdministrator) != kIOReturnSuccess) {
        return kIOReturnNotPrivileged;
    }

    AICNativeBridgeUserClient *client = OSTypeAlloc(AICNativeBridgeUserClient);
    if (!client) return kIOReturnNoMemory;
    if (!client->initWithTask(owningTask, securityID, type, properties)) {
        client->release();
        return kIOReturnError;
    }
    if (!client->attach(this)) {
        client->release();
        return kIOReturnError;
    }
    if (!client->start(this)) {
        client->detach(this);
        client->release();
        return kIOReturnError;
    }
    *handler = client;
    return kIOReturnSuccess;
}

extern "C" kern_return_t _start(kmod_info_t *, void *);
extern "C" kern_return_t _stop(kmod_info_t *, void *);
// libkmod delegates to these optional hooks; the probe has no custom hook.
extern "C" {
kmod_start_func_t *_realmain = nullptr;
kmod_stop_func_t *_antimain = nullptr;
}
KMOD_EXPLICIT_DECL(local.victor.AICNativeProbe, "0.0.19", _start, _stop)
