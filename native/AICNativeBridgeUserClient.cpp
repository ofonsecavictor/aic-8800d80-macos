#include "AICNativeBridgeUserClient.h"
#include "AICNativeBridgeProtocol.h"
#include <IOKit/IOLib.h>
#include <IOKit/IOMemoryDescriptor.h>
#include "AICNativeBatchTransfer.h"

// Defined by the controller. The service argument is checked before casting.
extern "C" IOReturn AICNativePublishState(IOService *service,
                                           const AICNativeRadioState *state);
extern "C" IOReturn AICNativeNextCommand(IOService *service,
                                          AICNativeCommand *command);
extern "C" IOReturn AICNativeSubmitReceivedFrame(
    IOService *service, const AICNativeFrame *frame);
extern "C" IOReturn AICNativeNextTransmitFrame(
    IOService *service, AICNativeFrame *frame);
extern "C" IOReturn AICNativeSubmitReceivedFrames(
    IOService *service, const AICNativeFrameBatch *batch);
extern "C" IOReturn AICNativeNextTransmitFrames(
    IOService *service, AICNativeFrameBatch *batch);
extern "C" IOReturn AICNativeNextScanRequest(
    IOService *service, AICNativeScanRequest *request);
extern "C" IOReturn AICNativeSubmitScanResult(
    IOService *service, const AICNativeScanResult *result);
extern "C" IOReturn AICNativeCompleteScan(
    IOService *service, const AICNativeScanCompletion *completion);
extern "C" IOReturn AICNativeSetScanBridgeEnabled(
    IOService *service, IOUserClient *client, bool enabled);
extern "C" IOReturn AICNativeNextJoinRequest(
    IOService *service, IOUserClient *client, AICNativeJoinRequest *request);
extern "C" IOReturn AICNativeCompleteJoin(
    IOService *service, IOUserClient *client,
    const AICNativeJoinCompletion *completion);
extern "C" IOReturn AICNativeNextLeaveCommand(
    IOService *service, IOUserClient *client, AICNativeCommand *command);

static void AICWipeJoin(void *buffer, size_t length) {
    volatile uint8_t *p = static_cast<volatile uint8_t *>(buffer);
    while (length--) *p++ = 0;
}

OSDefineMetaClassAndStructors(AICNativeBridgeUserClient, IOUserClient)

IOReturn AICNativeBridgeUserClient::externalMethod(
    uint32_t selector, IOExternalMethodArguments *arguments,
    IOExternalMethodDispatch *, OSObject *, void *) {
    if (!arguments) return kIOReturnBadArgument;
    if (selector == kAICNativeGetVersion) {
        if (arguments->scalarInputCount != 0 ||
            arguments->structureInputSize != 0 ||
            arguments->scalarOutputCount != 1 || !arguments->scalarOutput ||
            arguments->structureOutputSize != 0) {
            return kIOReturnBadArgument;
        }
        arguments->scalarOutput[0] = kAICNativeBridgeVersion;
        return kIOReturnSuccess;
    }
    if (selector == kAICNativePublishRadioState) {
        if (arguments->scalarInputCount != 0 ||
            arguments->scalarOutputCount != 0 ||
            arguments->structureOutputSize != 0 ||
            arguments->structureInputSize != sizeof(AICNativeRadioState) ||
            !arguments->structureInput) {
            IOLog("AICNative: state publish rejected argument shape\n");
            return kIOReturnBadArgument;
        }
        AICNativeRadioState state;
        bcopy(arguments->structureInput, &state, sizeof(state));
        if (!AICNativeRadioStateValid(state)) {
            IOLog("AICNative: state publish rejected invalid state\n");
            return kIOReturnBadArgument;
        }
        // The user client is attached directly to this controller. Use the
        // IOKit provider relationship instead of an optional service cache.
        IOService *controller = getProvider();
        IOReturn status = AICNativePublishState(controller, &state);
        if (status != kIOReturnSuccess)
            IOLog("AICNative: state publish failed: 0x%x, provider=%d\n",
                  status, controller != nullptr);
        return status;
    }
    if (selector == kAICNativeNextCommand) {
        if (arguments->scalarInputCount != 0 ||
            arguments->scalarOutputCount != 0 ||
            arguments->structureInputSize != 0 ||
            !arguments->structureOutput ||
            arguments->structureOutputSize < sizeof(AICNativeCommand)) {
            return kIOReturnBadArgument;
        }
        AICNativeCommand command = {};
        IOReturn status = AICNativeNextCommand(getProvider(), &command);
        if (status != kIOReturnSuccess) return status;
        if (!AICNativeCommandValid(command)) return kIOReturnError;
        bcopy(&command, arguments->structureOutput, sizeof(command));
        arguments->structureOutputSize = sizeof(command);
        return kIOReturnSuccess;
    }
    if (selector == kAICNativeSubmitFrame) {
        if (arguments->scalarInputCount != 0 ||
            arguments->scalarOutputCount != 0 ||
            arguments->structureOutputSize != 0 ||
            arguments->structureInputSize != sizeof(AICNativeFrame) ||
            !arguments->structureInput)
            return kIOReturnBadArgument;
        AICNativeFrame frame;
        bcopy(arguments->structureInput, &frame, sizeof(frame));
        return AICNativeSubmitReceivedFrame(getProvider(), &frame);
    }
    if (selector == kAICNativeNextFrame) {
        if (arguments->scalarInputCount != 0 ||
            arguments->scalarOutputCount != 0 ||
            arguments->structureInputSize != 0 ||
            !arguments->structureOutput ||
            arguments->structureOutputSize < sizeof(AICNativeFrame))
            return kIOReturnBadArgument;
        AICNativeFrame frame = {};
        IOReturn status = AICNativeNextTransmitFrame(getProvider(), &frame);
        if (status != kIOReturnSuccess) return status;
        if (!AICNativeFrameValid(frame, false)) return kIOReturnError;
        bcopy(&frame, arguments->structureOutput, sizeof(frame));
        arguments->structureOutputSize = sizeof(frame);
        return kIOReturnSuccess;
    }
    if (selector == kAICNativeSubmitFrameBatch) {
        if (!AICBatchInputValid(*arguments, sizeof(AICNativeFrameBatch)))
            return kIOReturnBadArgument;
        auto *batch = static_cast<AICNativeFrameBatch *>(
            IOMalloc(sizeof(AICNativeFrameBatch)));
        if (!batch) return kIOReturnNoMemory;
        if (!AICBatchRead(*arguments, batch, sizeof(*batch))) {
            bzero(batch, sizeof(*batch));
            IOFree(batch, sizeof(*batch));
            return kIOReturnBadArgument;
        }
        IOReturn status = AICNativeFrameBatchValid(*batch, true)
            ? AICNativeSubmitReceivedFrames(getProvider(), batch)
            : kIOReturnBadArgument;
        bzero(batch, sizeof(*batch));
        IOFree(batch, sizeof(*batch));
        return status;
    }
    if (selector == kAICNativeNextFrameBatch) {
        if (!AICBatchOutputValid(*arguments, sizeof(AICNativeFrameBatch)))
            return kIOReturnBadArgument;
        auto *batch = static_cast<AICNativeFrameBatch *>(
            IOMalloc(sizeof(AICNativeFrameBatch)));
        if (!batch) return kIOReturnNoMemory;
        bzero(batch, sizeof(*batch));
        IOReturn status = AICNativeNextTransmitFrames(getProvider(), batch);
        if (status == kIOReturnSuccess && !AICNativeFrameBatchValid(*batch, false))
            status = kIOReturnError;
        if (status == kIOReturnSuccess) {
            if (!AICBatchWrite(*arguments, batch, sizeof(*batch)))
                status = kIOReturnError;
        }
        bzero(batch, sizeof(*batch));
        IOFree(batch, sizeof(*batch));
        return status;
    }
    if (selector == kAICNativeNextScan) {
        if (arguments->scalarInputCount || arguments->scalarOutputCount ||
            arguments->structureInputSize || !arguments->structureOutput ||
            arguments->structureOutputSize < sizeof(AICNativeScanRequest))
            return kIOReturnBadArgument;
        AICNativeScanRequest request = {};
        IOReturn status = AICNativeNextScanRequest(getProvider(), &request);
        if (status != kIOReturnSuccess) return status;
        if (!AICNativeScanRequestValid(request)) return kIOReturnError;
        bcopy(&request, arguments->structureOutput, sizeof(request));
        arguments->structureOutputSize = sizeof(request);
        return kIOReturnSuccess;
    }
    if (selector == kAICNativeSubmitScanResult) {
        if (arguments->scalarInputCount || arguments->scalarOutputCount ||
            arguments->structureOutputSize ||
            arguments->structureInputSize != sizeof(AICNativeScanResult) ||
            !arguments->structureInput) return kIOReturnBadArgument;
        auto *result = static_cast<AICNativeScanResult *>(
            IOMalloc(sizeof(AICNativeScanResult)));
        if (!result) return kIOReturnNoMemory;
        bcopy(arguments->structureInput, result, sizeof(*result));
        IOReturn status = AICNativeSubmitScanResult(getProvider(), result);
        bzero(result, sizeof(*result));
        IOFree(result, sizeof(*result));
        return status;
    }
    if (selector == kAICNativeCompleteScan) {
        if (arguments->scalarInputCount || arguments->scalarOutputCount ||
            arguments->structureOutputSize ||
            arguments->structureInputSize != sizeof(AICNativeScanCompletion) ||
            !arguments->structureInput) return kIOReturnBadArgument;
        AICNativeScanCompletion completion = {};
        bcopy(arguments->structureInput, &completion, sizeof(completion));
        return AICNativeCompleteScan(getProvider(), &completion);
    }
    if (selector == kAICNativeEnableScanBridge) {
        if (arguments->scalarInputCount || arguments->scalarOutputCount ||
            arguments->structureInputSize || arguments->structureOutputSize)
            return kIOReturnBadArgument;
        return AICNativeSetScanBridgeEnabled(getProvider(), this, true);
    }
    if (selector == kAICNativeNextJoin) {
        if (arguments->scalarInputCount || arguments->scalarOutputCount ||
            arguments->structureInputSize || !arguments->structureOutput ||
            arguments->structureOutputSize < sizeof(AICNativeJoinRequest))
            return kIOReturnBadArgument;
        AICNativeJoinRequest request = {};
        IOReturn status = AICNativeNextJoinRequest(getProvider(), this, &request);
        if (status == kIOReturnSuccess) {
            if (!AICNativeJoinRequestValid(request)) status = kIOReturnError;
            else {
                bcopy(&request, arguments->structureOutput, sizeof(request));
                arguments->structureOutputSize = sizeof(request);
            }
        }
        AICWipeJoin(&request, sizeof(request));
        return status;
    }
    if (selector == kAICNativeCompleteJoin) {
        if (arguments->scalarInputCount || arguments->scalarOutputCount ||
            arguments->structureOutputSize ||
            arguments->structureInputSize != sizeof(AICNativeJoinCompletion) ||
            !arguments->structureInput) return kIOReturnBadArgument;
        AICNativeJoinCompletion completion = {};
        bcopy(arguments->structureInput, &completion, sizeof(completion));
        return AICNativeCompleteJoin(getProvider(), this, &completion);
    }
    if (selector == kAICNativeNextLeave) {
        if (arguments->scalarInputCount || arguments->scalarOutputCount ||
            arguments->structureInputSize || !arguments->structureOutput ||
            arguments->structureOutputSize < sizeof(AICNativeCommand))
            return kIOReturnBadArgument;
        AICNativeCommand command = {};
        IOReturn status = AICNativeNextLeaveCommand(getProvider(), this, &command);
        if (status != kIOReturnSuccess) return status;
        if (!AICNativeCommandValid(command) ||
            command.operation != kAICNativeLeave) return kIOReturnError;
        bcopy(&command, arguments->structureOutput, sizeof(command));
        arguments->structureOutputSize = sizeof(command);
        return kIOReturnSuccess;
    }
    return kIOReturnUnsupported;
}

IOReturn AICNativeBridgeUserClient::clientClose() {
    AICNativeSetScanBridgeEnabled(getProvider(), this, false);
    terminate();
    return kIOReturnSuccess;
}
