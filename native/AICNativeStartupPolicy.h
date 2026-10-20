#pragma once

// IONetworkController::start in Darwin 24H32 dereferences the native queue's
// null getThread() result when controller/provider workloops differ. This
// topology must be checked before calling the superclass start method.
template <typename WorkLoop>
inline bool AICNativeSharedWorkLoop(WorkLoop *controller, WorkLoop *provider) {
    return controller && controller == provider;
}
