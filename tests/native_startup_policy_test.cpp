#include "../native/AICNativeStartupPolicy.h"

#include <assert.h>

struct Loop { void *thread; };

int main() {
    Loop usb = {reinterpret_cast<void *>(1)};
    Loop native = {nullptr};
    Loop other = {nullptr};
    // The old direct-USB topology would enter IONetworkController's thread
    // adjustment path with native.thread == nullptr on this Darwin build.
    assert(!AICNativeSharedWorkLoop(&native, &usb));
    assert(!AICNativeSharedWorkLoop(&native, &other));
    assert(!AICNativeSharedWorkLoop(static_cast<Loop *>(nullptr),
                                    static_cast<Loop *>(nullptr)));
    assert(AICNativeSharedWorkLoop(&native, &native));
    return 0;
}
