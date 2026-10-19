#pragma once

#include <IOKit/IOUserClient.h>

// Compile-only control plane. It accepts radio state, never USB/RF commands.
class AICNativeBridgeUserClient final : public IOUserClient {
    OSDeclareDefaultStructors(AICNativeBridgeUserClient)

public:
    IOReturn externalMethod(uint32_t selector, IOExternalMethodArguments *arguments,
                            IOExternalMethodDispatch *dispatch = nullptr,
                            OSObject *target = nullptr,
                            void *reference = nullptr) override;
    IOReturn clientClose() override;
};
