import CoreWLAN
import Foundation

guard CommandLine.arguments.count == 2 else {
    fputs("Usage: native_scan_request <interface>\n", stderr)
    exit(2)
}

let name = CommandLine.arguments[1]
guard let interface = CWWiFiClient.shared().interface(withName: name) else {
    fputs("CoreWLAN interface unavailable\n", stderr)
    exit(3)
}

do {
    print("COREWLAN_POWER_BEFORE=\(interface.powerOn())")
    if !interface.powerOn() {
        try interface.setPower(true)
    }
    print("COREWLAN_POWER_AFTER=\(interface.powerOn())")
    let networks = try interface.scanForNetworks(withSSID: nil)
    // Do not print SSIDs, BSSIDs, or other identifying scan data.
    print("COREWLAN_SCAN_COUNT=\(networks.count)")
} catch {
    print("COREWLAN_SCAN_ERROR=\(error.localizedDescription)")
    exit(4)
}
