#pragma once

#include <macOS15/IOSkywalkEthernetInterface.h>

// Compile-only declarations for the queue factories exported by the local
// macOS 15 IOSkywalkFamily. The MacKernelSDK Rx-submission header has invalid
// C++ declarations, so use the verified Mach-O symbol names without copying
// its class layout into this driver. No queue is created by including this.

#include <IOSkywalkPacketBufferPool.h>
#include <skywalk/packet/os_packet.h>

// The Airport header defines IOSkywalkPacketBufferPool. Prevent the SDK's
// second, incompatible declaration when it includes the queue base.
#ifndef _IOSKYWALKPACKETBUFFERPOOL_H
#define _IOSKYWALKPACKETBUFFERPOOL_H
#endif
#include <IOKit/skywalk/IOSkywalkPacketQueue.h>

using AICSkywalkSubmitAction = UInt32 (*)(
    OSObject *, IOSkywalkPacketQueue *, IOSkywalkPacket *const *, UInt32,
    void *);
using AICSkywalkCompleteAction = UInt32 (*)(
    OSObject *, IOSkywalkPacketQueue *, IOSkywalkPacket **, UInt32,
    void *);

extern "C" IOSkywalkPacketQueue *AICCreateTxSubmissionQueue(
    IOSkywalkPacketBufferPool *, UInt32, UInt32, OSObject *,
    AICSkywalkSubmitAction, void *, IOOptionBits)
    __asm__("__ZN26IOSkywalkTxSubmissionQueue8withPoolEP25IOSkywalkPacketBufferPooljjP8OSObjectPFjS3_PS_PKP15IOSkywalkPacketjPvES9_j");

extern "C" IOSkywalkPacketQueue *AICCreateTxCompletionQueue(
    IOSkywalkPacketBufferPool *, UInt32, UInt32, OSObject *,
    AICSkywalkCompleteAction, void *, IOOptionBits)
    __asm__("__ZN26IOSkywalkTxCompletionQueue8withPoolEP25IOSkywalkPacketBufferPooljjP8OSObjectPFjS3_PS_PP15IOSkywalkPacketjPvES8_j");

extern "C" IOSkywalkPacketQueue *AICCreateRxSubmissionQueue(
    IOSkywalkPacketBufferPool *, UInt32, UInt32, UInt32, OSObject *,
    AICSkywalkSubmitAction, void *, IOOptionBits)
    __asm__("__ZN26IOSkywalkRxSubmissionQueue8withPoolEP25IOSkywalkPacketBufferPooljjjP8OSObjectPFjS3_PS_PKP15IOSkywalkPacketjPvES9_j");

extern "C" IOSkywalkPacketQueue *AICCreateRxCompletionQueue(
    IOSkywalkPacketBufferPool *, UInt32, UInt32, OSObject *,
    AICSkywalkCompleteAction, void *, IOOptionBits)
    __asm__("__ZN26IOSkywalkRxCompletionQueue8withPoolEP25IOSkywalkPacketBufferPooljjP8OSObjectPFjS3_PS_PP15IOSkywalkPacketjPvES8_j");

static_assert(sizeof(IOSkywalkPacketBufferPool::PoolOptions) == 32,
              "Sequoia Skywalk pool option ABI");

// The pinned third-party header declares this private method as bool, but
// the local Sequoia binary returns IOReturn. Call the exported ABI directly
// so success (zero) is not misinterpreted as false.
extern "C" IOReturn AICRegisterSkywalkEthernet(
    IOSkywalkEthernetInterface *,
    const IOSkywalkEthernetInterface::RegistrationInfo *,
    IOSkywalkPacketQueue **, UInt32, IOSkywalkPacketBufferPool *,
    IOSkywalkPacketBufferPool *, IOOptionBits)
    __asm__("__ZN26IOSkywalkEthernetInterface25registerEthernetInterfaceEPKNS_16RegistrationInfoEPP20IOSkywalkPacketQueuejP25IOSkywalkPacketBufferPoolS7_j");
