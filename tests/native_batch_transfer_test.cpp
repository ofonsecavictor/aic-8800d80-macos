#include "../native/AICNativeBatchTransfer.h"
#include <cassert>
#include <vector>
#include <stdexcept>

struct Descriptor {
    std::vector<unsigned char> data;
    bool shortCopy = false;
    bool wired = false;
    bool failPrepare = false;
    bool failComplete = false;
    unsigned preparations = 0, completions = 0, transfers = 0;
    int prepare() {
        ++preparations;
        assert(!wired);
        if (failPrepare) return -1;
        wired = true;
        return 0;
    }
    int complete() {
        assert(wired);
        ++completions;
        wired = false;
        return failComplete ? -1 : 0;
    }
    size_t getLength() const { return data.size(); }
    size_t readBytes(size_t, void *p, size_t n) {
        if (!wired) throw std::logic_error("REGRESSION: readBytes on unprepared descriptor");
        ++transfers;
        if (shortCopy) return 0;
        memcpy(p, data.data(), n); return n;
    }
    size_t writeBytes(size_t, const void *p, size_t n) {
        if (!wired) throw std::logic_error("REGRESSION: writeBytes on unprepared descriptor (panic path)");
        ++transfers;
        if (shortCopy) return 0;
        memcpy(data.data(), p, n); return n;
    }
};
struct Arguments {
    unsigned scalarInputCount = 0, scalarOutputCount = 0;
    const void *structureInput = nullptr;
    size_t structureInputSize = 0;
    Descriptor *structureInputDescriptor = nullptr;
    void *structureOutput = nullptr;
    size_t structureOutputSize = 0;
    Descriptor *structureOutputDescriptor = nullptr;
    size_t structureOutputDescriptorSize = 0;
};

int main() {
    constexpr size_t n = 24648;
    Descriptor input{std::vector<unsigned char>(n, 0x5a)};
    Descriptor output{std::vector<unsigned char>(n)};
    std::vector<unsigned char> buffer(n);
    Arguments args;
    // Exercise the exact write path present in both real panic backtraces.
    args.structureOutputDescriptor = &output;
    assert(AICBatchWrite(args, buffer.data(), n));
    assert(output.preparations == 1 && output.completions == 1 && !output.wired);
    args = {};
    args.structureInputDescriptor = &input;
    assert(AICBatchRead(args, buffer.data(), n));
    assert(buffer == input.data);
    input.shortCopy = true;
    assert(!AICBatchRead(args, buffer.data(), n));
    input.shortCopy = false;
    args.structureInput = buffer.data();
    // Mach supplies an inline storage pointer even when its count is zero.
    assert(AICBatchRead(args, buffer.data(), n));
    args.structureInputSize = 1;
    assert(!AICBatchInputValid(args, n)); // Ambiguous input.
    args.structureInputDescriptor = nullptr;
    args.structureInputSize = n - 1;
    assert(!AICBatchInputValid(args, n));
    args.structureInputSize = n;
    assert(AICBatchRead(args, output.data.data(), n));
    args = {};
    args.structureOutputDescriptor = &output;
    args.structureOutput = buffer.data(); // Non-null, zero-length inline area.
    assert(AICBatchWrite(args, buffer.data(), n));
    assert(args.structureOutputDescriptorSize == n);
    assert(output.data == input.data);
    args.structureOutputSize = 1;
    assert(!AICBatchOutputValid(args, n));
    args.structureOutputSize = 0;
    output.shortCopy = true;
    assert(!AICBatchWrite(args, buffer.data(), n));
    output.shortCopy = false;
    output.data.resize(n - 1);
    assert(!AICBatchOutputValid(args, n));
    args.structureOutputDescriptor = nullptr;
    args.structureOutput = buffer.data();
    args.structureOutputSize = n;
    assert(AICBatchWrite(args, input.data.data(), n));
    args.scalarInputCount = 1;
    assert(!AICBatchOutputValid(args, n));

    // Fault injection must release wiring on every post-prepare exit, and
    // never transfer/complete when prepare fails. Exercise both directions.
    for (bool reading : {false, true}) {
        for (int failure = 0; failure < 4; ++failure) {
            Descriptor descriptor{std::vector<unsigned char>(n)};
            descriptor.failPrepare = failure == 1;
            descriptor.shortCopy = failure == 2;
            descriptor.failComplete = failure == 3;
            Arguments test;
            if (reading) test.structureInputDescriptor = &descriptor;
            else test.structureOutputDescriptor = &descriptor;
            const bool ok = reading ? AICBatchRead(test, buffer.data(), n)
                                    : AICBatchWrite(test, buffer.data(), n);
            assert(ok == (failure == 0));
            assert(descriptor.preparations == 1);
            assert(descriptor.transfers == (failure == 1 ? 0u : 1u));
            assert(descriptor.completions == (failure == 1 ? 0u : 1u));
            assert(!descriptor.wired);
            if (!reading && !ok) assert(test.structureOutputDescriptorSize == 0);
        }
    }
    Descriptor stress{std::vector<unsigned char>(n)};
    Arguments read, write;
    read.structureInputDescriptor = &stress;
    write.structureOutputDescriptor = &stress;
    for (unsigned i = 0; i < 10000; ++i) {
        assert(AICBatchWrite(write, buffer.data(), n));
        assert(AICBatchRead(read, buffer.data(), n));
        assert(!stress.wired);
    }
    assert(stress.preparations == 20000 && stress.completions == 20000);
    assert(!AICBatchWrite(write, nullptr, n));
    assert(!AICBatchRead(read, nullptr, n));
    assert(stress.preparations == 20000);
}
