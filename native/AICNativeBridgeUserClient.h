#pragma once

#include <IOKit/IOUserClient.h>

// Compile-only control plane. Frame transport is bounded and remains unused
// by any IO80211 interface; this class does not own the USB device.
class AICNativeBridgeUserClient final : public IOUserClient {
    OSDeclareDefaultStructors(AICNativeBridgeUserClient)

public:
    IOReturn externalMethod(uint32_t selector, IOExternalMethodArguments *arguments,
                            IOExternalMethodDispatch *dispatch = nullptr,
                            OSObject *target = nullptr,
                            void *reference = nullptr) override;
    IOReturn clientClose() override;
};
