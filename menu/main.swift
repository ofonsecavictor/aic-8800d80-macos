import AppKit
import Darwin
import Foundation

final class NetworkButton: NSButton {
    var contextMenu: (() -> NSMenu)?
    override func rightMouseDown(with event: NSEvent) {
        if let menu = contextMenu?() { NSMenu.popUpContextMenu(menu, with: event, for: self) }
    }
    override func mouseDown(with event: NSEvent) {
        if event.modifierFlags.contains(.control) { rightMouseDown(with: event) }
        else { super.mouseDown(with: event) }
    }
}

final class AppDelegate: NSObject, NSApplicationDelegate {
    private struct NetworkReport: Decodable {
        let updated_unix: Double?
        let configured_ssid: String
        let configured_band: Int?
        let networks: [Network]
    }
    private struct Network: Decodable {
        let ssid: String
        let rssi: Int
        let channel: Int?
        let band: String?
        let band_id: Int?
        let known: Bool?
        let connectable: Bool?
        let secured: Bool
    }
    private struct ControlResponse: Decodable {
        let ok: Bool
        let message: String?
        let needs_password: Bool?
        let enabled: Bool?
        let native_mode: Bool?
        let connected: Bool?
        let dongle_present: Bool?
        let connected_ssid: String?
        let connected_band: Int?
        let scan_deferred: Bool?
    }

    private let controlPath = "/private/tmp/aic-wifi-control.sock"
    private let networksPath = "/Library/Application Support/AIC88M80Driver/wifi/redes-disponiveis.json"
    private let popover = NSPopover()
    private var statusItem: NSStatusItem!
    private var report: NetworkReport?
    private var serviceStatus: ControlResponse?
    private var displayedNetworks: [Network] = []
    private var showOtherNetworks = false
    private var busy = false
    private var scanStartedAt: Double?
    private var scanOnOpenPending = false
    private var passwordPromptOpen = false
    private var connecting: Network?
    private var connectingSince: Date?
    private var connectionError: String?
    private var scanNotice: String?
    private var timer: Timer?

    func applicationDidFinishLaunching(_ notification: Notification) {
        NSApp.setActivationPolicy(.accessory)
        statusItem = NSStatusBar.system.statusItem(withLength: NSStatusItem.squareLength)
        guard let button = statusItem.button else { return }
        button.image = NSImage(systemSymbolName: "wifi", accessibilityDescription: "Wi-Fi")
        button.toolTip = "Wi-Fi"
        button.target = self
        button.action = #selector(togglePopover)

        popover.behavior = .transient
        popover.animates = true
        refreshStatus()
        timer = Timer.scheduledTimer(withTimeInterval: 2, repeats: true) { [weak self] _ in
            self?.refreshStatus()
        }
    }

    @objc private func togglePopover() {
        if popover.isShown {
            popover.performClose(nil)
            return
        }
        // On first use there is no preferred network; show scan results
        // immediately instead of hiding every unknown network.
        showOtherNetworks = report?.configured_ssid.isEmpty ?? true
        scanOnOpenPending = true
        rebuildPanel()
        guard let button = statusItem.button else { return }
        NSApp.activate(ignoringOtherApps: true)
        popover.show(relativeTo: button.bounds, of: button, preferredEdge: .minY)
        DispatchQueue.main.async { [weak self] in
            self?.popover.contentViewController?.view.window?.makeKey()
        }
        refreshStatus()
    }

    private func readNetworks() -> NetworkReport? {
        guard let data = try? Data(contentsOf: URL(fileURLWithPath: networksPath)) else { return nil }
        return try? JSONDecoder().decode(NetworkReport.self, from: data)
    }

    private func refreshStatus() {
        DispatchQueue.global(qos: .utility).async { [weak self] in
            guard let self else { return }
            let status = self.control(["action": "status"])
            let networks = self.readNetworks()
            DispatchQueue.main.async {
                self.serviceStatus = status
                self.report = networks
                if let started = self.scanStartedAt,
                    (networks?.updated_unix ?? 0) > started ||
                    Date().timeIntervalSince1970 - started > 40 {
                    self.scanStartedAt = nil
                    self.busy = false
                }
                if let connecting = self.connecting {
                    if status?.connected == true && status?.connected_ssid == connecting.ssid &&
                        status?.connected_band == connecting.band_id {
                        self.connecting = nil
                        self.connectingSince = nil
                        self.connectionError = nil
                    } else if let started = self.connectingSince, Date().timeIntervalSince(started) > 60 {
                        self.connecting = nil
                        self.connectingSince = nil
                        self.connectionError = "A conexão demorou demais. Tente novamente."
                    }
                }
                self.updateStatusIcon()
                if self.popover.isShown && !self.passwordPromptOpen { self.rebuildPanel() }
                if self.scanOnOpenPending {
                    self.scanOnOpenPending = false
                    if status?.enabled == true && status?.dongle_present == true &&
                        status?.native_mode != true {
                        self.requestScan()
                    }
                }
            }
        }
    }

    private func updateStatusIcon() {
        let available = serviceStatus?.ok == true
        let nativeMode = serviceStatus?.native_mode == true
        let enabled = serviceStatus?.enabled == true
        let connected = serviceStatus?.connected == true
        let present = serviceStatus?.dongle_present == true
        let name = connected || (enabled && present) ? "wifi" : "wifi.slash"
        if connected, let current = report?.networks.first(where: matchesConfigured) {
            let strength = max(0, min(1, Double(current.rssi + 90) / 50.0))
            statusItem.button?.image = NSImage(systemSymbolName: name, variableValue: strength,
                accessibilityDescription: "Wi-Fi conectado")
        } else {
            statusItem.button?.image = NSImage(systemSymbolName: name, accessibilityDescription: "Wi-Fi")
        }
        statusItem.button?.appearsDisabled = !available || !present
        statusItem.button?.toolTip = nativeMode ? "Use o Wi-Fi do macOS" : !present ? "Adaptador Wi-Fi não conectado" :
            (connected ? "Wi-Fi conectado" : (enabled ? "Wi-Fi conectando" : "Wi-Fi desativado"))
    }

    private func label(_ text: String, size: CGFloat, weight: NSFont.Weight, color: NSColor = .labelColor) -> NSTextField {
        let field = NSTextField(labelWithString: text)
        field.font = .systemFont(ofSize: size, weight: weight)
        field.textColor = color
        field.lineBreakMode = .byTruncatingTail
        return field
    }

    private func separator() -> NSBox {
        let box = NSBox()
        box.boxType = .separator
        box.translatesAutoresizingMaskIntoConstraints = false
        box.heightAnchor.constraint(equalToConstant: 1).isActive = true
        return box
    }

    private func section(_ title: String) -> NSTextField {
        let field = label(title, size: 11, weight: .semibold, color: .secondaryLabelColor)
        field.stringValue = title.uppercased()
        return field
    }

    private func unique(_ networks: [Network]) -> [Network] {
        var seen = Set<String>()
        return networks.filter { seen.insert("\($0.ssid)\u{0}\($0.band_id ?? -1)").inserted }
    }

    private func matchesConfigured(_ network: Network) -> Bool {
        guard let report else { return false }
        return network.ssid == report.configured_ssid &&
            (report.configured_band == nil || network.band_id == report.configured_band)
    }

    private func networkButton(_ network: Network, selected: Bool, duplicateName: Bool) -> NSView {
        let loading = connecting?.ssid == network.ssid && connecting?.band_id == network.band_id
        let suffix = duplicateName ? "  \(network.band ?? "")" : ""
        let unavailable = network.connectable == false ? "  Indisponível" : ""
        let button = NetworkButton(title: "",
            target: self, action: #selector(selectNetwork(_:)))
        button.contextMenu = { [weak self] in self?.networkMenu(network, selected: selected) ?? NSMenu() }
        button.tag = displayedNetworks.count
        displayedNetworks.append(network)
        button.isBordered = false
        button.bezelStyle = .inline
        button.alignment = .left
        button.font = .systemFont(ofSize: 13)
        let textColor = selected ? NSColor.controlAccentColor : NSColor.labelColor
        let title = NSMutableAttributedString(string: network.ssid + suffix + unavailable,
            attributes: [.font: NSFont.systemFont(ofSize: 13), .foregroundColor: textColor])
        func appendSymbol(_ name: String) {
            guard let image = NSImage(systemSymbolName: name, accessibilityDescription: nil)?
                .withSymbolConfiguration(.init(pointSize: 11, weight: .semibold)) else { return }
            image.isTemplate = true
            let attachment = NSTextAttachment()
            attachment.image = image
            title.append(NSAttributedString(string: "  "))
            title.append(NSAttributedString(attachment: attachment))
        }
        if network.secured { appendSymbol("lock.fill") }
        if selected { appendSymbol("checkmark") }
        button.attributedTitle = title
        button.imagePosition = .imageLeading
        let strength = max(0, min(1, Double(network.rssi + 90) / 50.0))
        button.image = NSImage(systemSymbolName: "wifi", variableValue: strength,
            accessibilityDescription: "Sinal Wi-Fi")
        button.contentTintColor = selected ? .controlAccentColor : .labelColor
        button.isEnabled = !loading && network.secured && network.connectable != false && network.band_id != nil
        button.toolTip = [network.band, network.channel.map { "canal \($0)" }].compactMap { $0 }.joined(separator: ", ")
        button.translatesAutoresizingMaskIntoConstraints = false
        button.heightAnchor.constraint(equalToConstant: 30).isActive = true
        guard loading else { return button }
        button.widthAnchor.constraint(equalToConstant: 304).isActive = true
        let progress = NSProgressIndicator()
        progress.style = .spinning
        progress.controlSize = .small
        progress.startAnimation(nil)
        progress.toolTip = "Conectando a \(network.ssid)"
        let row = NSStackView(views: [button, progress])
        row.orientation = .horizontal
        row.alignment = .centerY
        row.spacing = 8
        row.widthAnchor.constraint(equalToConstant: 332).isActive = true
        row.heightAnchor.constraint(equalToConstant: 30).isActive = true
        return row
    }

    private func rebuildPanel() {
        displayedNetworks.removeAll()
        let root = NSVisualEffectView()
        root.material = .popover
        root.blendingMode = .behindWindow
        root.state = .active

        let stack = NSStackView()
        stack.orientation = .vertical
        stack.alignment = .leading
        stack.spacing = 7
        stack.edgeInsets = NSEdgeInsets(top: 14, left: 14, bottom: 12, right: 14)
        stack.translatesAutoresizingMaskIntoConstraints = false
        root.addSubview(stack)
        NSLayoutConstraint.activate([
            stack.leadingAnchor.constraint(equalTo: root.leadingAnchor),
            stack.trailingAnchor.constraint(equalTo: root.trailingAnchor),
            stack.topAnchor.constraint(equalTo: root.topAnchor),
            stack.bottomAnchor.constraint(equalTo: root.bottomAnchor)
        ])

        let header = NSStackView()
        header.orientation = .horizontal
        header.alignment = .centerY
        let title = label(serviceStatus?.native_mode == true ? "AIC (reserva)" : "Wi-Fi",
            size: 15, weight: .semibold)
        let toggle = NSSwitch()
        toggle.state = serviceStatus?.enabled == true ? .on : .off
        toggle.isEnabled = serviceStatus?.ok == true
        toggle.target = self
        toggle.action = #selector(togglePower(_:))
        header.addArrangedSubview(title)
        header.addArrangedSubview(NSView())
        header.addArrangedSubview(toggle)
        header.translatesAutoresizingMaskIntoConstraints = false
        header.widthAnchor.constraint(equalToConstant: 332).isActive = true
        stack.addArrangedSubview(header)
        stack.addArrangedSubview(separator())

        guard serviceStatus?.ok == true else {
            stack.addArrangedSubview(label("O serviço Wi-Fi não está disponível.", size: 13, weight: .regular, color: .secondaryLabelColor))
            installPanel(root, stack: stack)
            return
        }
        if serviceStatus?.native_mode == true {
            stack.addArrangedSubview(label("Wi-Fi nativo independente. Use o menu do macOS para ligar, buscar redes e conectar.",
                size: 13, weight: .regular, color: .secondaryLabelColor))
            installPanel(root, stack: stack)
            return
        }
        guard serviceStatus?.enabled == true else {
            stack.addArrangedSubview(label("Wi-Fi desativado", size: 13, weight: .regular, color: .secondaryLabelColor))
            installPanel(root, stack: stack)
            return
        }
        guard serviceStatus?.dongle_present == true else {
            let row = NSStackView(views: [
                NSImageView(image: NSImage(systemSymbolName: "externaldrive.badge.xmark",
                    accessibilityDescription: nil) ?? NSImage()),
                label("Conecte o adaptador Wi-Fi", size: 13, weight: .regular,
                    color: .secondaryLabelColor)
            ])
            row.orientation = .horizontal
            row.spacing = 8
            stack.addArrangedSubview(row)
            installPanel(root, stack: stack)
            return
        }
        if busy {
            let progress = NSProgressIndicator()
            progress.style = .spinning
            progress.controlSize = .small
            progress.startAnimation(nil)
            let row = NSStackView(views: [progress, label("Buscando redes…", size: 13, weight: .regular, color: .secondaryLabelColor)])
            row.orientation = .horizontal
            row.spacing = 8
            stack.addArrangedSubview(row)
        }
        if let scanNotice {
            stack.addArrangedSubview(label(scanNotice, size: 12, weight: .regular,
                color: .secondaryLabelColor))
        }
        if let connectionError {
            stack.addArrangedSubview(label(connectionError, size: 12, weight: .regular,
                color: .systemRed))
        }

        let networks = unique(report?.networks ?? [])
        let counts = Dictionary(grouping: networks, by: { $0.ssid }).mapValues(\.count)
        let current = networks.first(where: matchesConfigured)
        if let current {
            let connected = serviceStatus?.connected == true &&
                serviceStatus?.connected_ssid == current.ssid &&
                serviceStatus?.connected_band == current.band_id
            stack.addArrangedSubview(section(connected ? "Rede conectada" : "Rede preferida"))
            // Keep the configured network actionable while disconnected.  The
            // previous filter removed it from the rest of the list, leaving no
            // way to supply its password after a reboot.
            stack.addArrangedSubview(networkButton(current, selected: connected,
                duplicateName: (counts[current.ssid] ?? 0) > 1))
        }

        let remaining = networks.filter { network in
            if let current, network.ssid == current.ssid && network.band_id == current.band_id { return false }
            let known = network.known == true || matchesConfigured(network)
            return showOtherNetworks ? !known : known
        }
        if !remaining.isEmpty {
            stack.addArrangedSubview(section(showOtherNetworks ? "Outras redes" : "Redes conhecidas"))
            for network in remaining.prefix(10) {
                stack.addArrangedSubview(networkButton(network, selected: false, duplicateName: (counts[network.ssid] ?? 0) > 1))
            }
        }

        stack.addArrangedSubview(separator())
        let other = NSButton(title: showOtherNetworks ? "Atualizar Redes" : "Outras Redes…",
            target: self, action: #selector(showOther(_:)))
        other.isBordered = false
        other.bezelStyle = .inline
        other.font = .systemFont(ofSize: 13)
        other.alignment = .left
        other.image = NSImage(systemSymbolName: showOtherNetworks ? "arrow.clockwise" : "chevron.right",
            accessibilityDescription: nil)
        other.imagePosition = .imageTrailing
        other.isEnabled = !busy
        other.translatesAutoresizingMaskIntoConstraints = false
        other.widthAnchor.constraint(equalToConstant: 332).isActive = true
        other.heightAnchor.constraint(equalToConstant: 28).isActive = true
        stack.addArrangedSubview(other)
        installPanel(root, stack: stack)
    }

    private func installPanel(_ root: NSView, stack: NSStackView) {
        let controller = NSViewController()
        controller.view = root
        popover.contentViewController = controller
        root.layoutSubtreeIfNeeded()
        let height = max(120, min(500, stack.fittingSize.height))
        popover.contentSize = NSSize(width: 360, height: height)
    }

    @objc private func togglePower(_ sender: NSSwitch) {
        send(["action": "power", "enabled": sender.state == .on], searching: false)
    }

    @objc private func showOther(_ sender: NSButton) {
        showOtherNetworks = true
        requestScan()
    }

    private func requestScan() {
        guard serviceStatus?.native_mode != true else { return }
        guard !busy else { return }
        scanNotice = nil
        scanStartedAt = Date().timeIntervalSince1970
        send(["action": "scan"], searching: true)
    }

    @objc private func selectNetwork(_ sender: NSButton) {
        guard sender.tag >= 0, sender.tag < displayedNetworks.count else { return }
        connect(displayedNetworks[sender.tag])
    }

    private func connect(_ network: Network) {
        guard let band = network.band_id else { return }
        connecting = network
        connectingSince = Date()
        connectionError = nil
        rebuildPanel()
        send(["action": "select", "ssid": network.ssid, "band": band], searching: false) { [weak self] response in
            if response.needs_password == true { self?.askPassword(for: network, band: band) }
            else if !response.ok { self?.connectionFailed(response.message ?? "Não foi possível conectar.") }
        }
    }

    private func connectionFailed(_ message: String) {
        connecting = nil
        connectingSince = nil
        connectionError = message
        rebuildPanel()
    }

    private func networkMenu(_ network: Network, selected: Bool) -> NSMenu {
        let menu = NSMenu()
        menu.autoenablesItems = false
        let connect = NSMenuItem(title: selected ? "Conectado" : "Conectar", action: #selector(contextConnect(_:)), keyEquivalent: "")
        connect.target = self
        connect.representedObject = network
        connect.isEnabled = !selected && network.secured && network.connectable != false && network.band_id != nil
        menu.addItem(connect)
        if network.known == true || matchesConfigured(network) {
            menu.addItem(.separator())
            let forget = NSMenuItem(title: "Esquecer rede…", action: #selector(contextForget(_:)), keyEquivalent: "")
            forget.target = self
            forget.representedObject = network
            menu.addItem(forget)
        }
        return menu
    }

    @objc private func contextConnect(_ sender: NSMenuItem) {
        guard let network = sender.representedObject as? Network else { return }
        connect(network)
    }

    @objc private func contextForget(_ sender: NSMenuItem) {
        guard let network = sender.representedObject as? Network else { return }
        popover.performClose(nil)
        let alert = NSAlert()
        alert.messageText = "Esquecer a rede “\(network.ssid)”?"
        alert.informativeText = "A senha salva será removida. Para conectar novamente, será necessário informá-la. Se esta for a rede atual, a conexão será encerrada."
        alert.addButton(withTitle: "Esquecer rede")
        alert.addButton(withTitle: "Cancelar")
        NSApp.activate(ignoringOtherApps: true)
        guard alert.runModal() == .alertFirstButtonReturn else { return }
        send(["action": "forget", "ssid": network.ssid], searching: false)
    }

    private func send(_ request: [String: Any], searching: Bool,
                      completion: ((ControlResponse) -> Void)? = nil) {
        busy = searching
        rebuildPanel()
        DispatchQueue.global(qos: .userInitiated).async { [weak self] in
            guard let self else { return }
            let fallback = ControlResponse(ok: false, message: "Serviço Wi-Fi indisponível.",
                needs_password: nil, enabled: nil, native_mode: nil,
                connected: nil, dongle_present: nil,
                connected_ssid: nil, connected_band: nil, scan_deferred: nil)
            let response = self.control(request) ?? fallback
            DispatchQueue.main.async {
                // The socket acknowledges a scan before the radio finishes it.
                if response.scan_deferred == true {
                    self.scanNotice = "Busca completa pausada para preservar a conexão."
                    self.rebuildPanel()
                }
                if !(searching && response.ok && response.scan_deferred != true) {
                    self.busy = false
                    self.scanStartedAt = nil
                }
                if !response.ok && response.needs_password != true &&
                    request["action"] as? String != "select" {
                    if searching {
                        self.connectionError = response.message ?? "Não foi possível buscar redes."
                        self.rebuildPanel()
                    } else {
                        self.showError(response.message ?? "Não foi possível concluir a operação.")
                    }
                }
                completion?(response)
                self.refreshStatus()
            }
        }
    }

    private func askPassword(for network: Network, band: Int) {
        let alert = NSAlert()
        alert.messageText = "A rede “\(network.ssid)” requer uma senha WPA2."
        alert.informativeText = "Digite a senha da rede Wi-Fi."
        alert.addButton(withTitle: "Conectar")
        alert.addButton(withTitle: "Cancelar")
        let password = NSSecureTextField(frame: NSRect(x: 0, y: 0, width: 300, height: 24))
        password.placeholderString = "Senha"
        alert.accessoryView = password
        NSApp.activate(ignoringOtherApps: true)
        guard let window = popover.contentViewController?.view.window else {
            connectionFailed("O painel Wi-Fi não está disponível.")
            return
        }
        passwordPromptOpen = true
        alert.beginSheetModal(for: window) { [weak self] answer in
            guard let self else { return }
            self.passwordPromptOpen = false
            guard answer == .alertFirstButtonReturn, !password.stringValue.isEmpty else {
                self.connectionFailed("Conexão cancelada.")
                return
            }
            self.submitPassword(password.stringValue, for: network, band: band)
            password.stringValue = ""
        }
    }

    private func submitPassword(_ supplied: String, for network: Network, band: Int) {
        DispatchQueue.global(qos: .userInitiated).async { [weak self] in
            do {
                guard let self else { return }
                let pmk = try self.derivePMK(password: supplied, ssid: network.ssid)
                let response = self.control(["action": "select", "ssid": network.ssid, "band": band, "pmk": pmk])
                DispatchQueue.main.async {
                    if response?.ok != true {
                        self.connectionFailed(response?.message ?? "Não foi possível conectar.")
                    }
                    self.refreshStatus()
                }
            } catch {
                DispatchQueue.main.async { [weak self] in self?.connectionFailed(error.localizedDescription) }
            }
        }
    }

    private func derivePMK(password: String, ssid: String) throws -> String {
        let process = Process()
        let input = Pipe(), output = Pipe()
        process.executableURL = URL(fileURLWithPath: "/usr/bin/python3")
        process.arguments = ["-c", "import hashlib,sys; p=sys.stdin.buffer.read(); print(hashlib.pbkdf2_hmac('sha1',p,sys.argv[1].encode('utf-8'),4096,32).hex())", ssid]
        process.standardInput = input
        process.standardOutput = output
        try process.run()
        input.fileHandleForWriting.write(Data(password.utf8))
        try input.fileHandleForWriting.close()
        process.waitUntilExit()
        let value = String(data: output.fileHandleForReading.readDataToEndOfFile(), encoding: .utf8)?
            .trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
        guard process.terminationStatus == 0, value.count == 64 else {
            throw NSError(domain: "AICWiFi", code: 1,
                userInfo: [NSLocalizedDescriptionKey: "Não foi possível preparar a senha."])
        }
        return value
    }

    private func control(_ request: [String: Any]) -> ControlResponse? {
        guard JSONSerialization.isValidJSONObject(request),
              var data = try? JSONSerialization.data(withJSONObject: request) else { return nil }
        data.append(0x0a)
        let descriptor = Darwin.socket(AF_UNIX, SOCK_STREAM, 0)
        guard descriptor >= 0 else { return nil }
        defer { Darwin.close(descriptor) }
        var noSigPipe: Int32 = 1
        _ = withUnsafePointer(to: &noSigPipe) {
            Darwin.setsockopt(descriptor, SOL_SOCKET, SO_NOSIGPIPE, $0,
                socklen_t(MemoryLayout<Int32>.size))
        }
        var address = sockaddr_un()
        address.sun_len = UInt8(MemoryLayout<sockaddr_un>.size)
        address.sun_family = sa_family_t(AF_UNIX)
        let copied = controlPath.utf8CString.withUnsafeBytes { source -> Bool in
            withUnsafeMutableBytes(of: &address.sun_path) { destination in
                guard source.count <= destination.count else { return false }
                destination.copyBytes(from: source)
                return true
            }
        }
        guard copied else { return nil }
        let connected = withUnsafePointer(to: &address) {
            $0.withMemoryRebound(to: sockaddr.self, capacity: 1) {
                Darwin.connect(descriptor, $0, socklen_t(MemoryLayout<sockaddr_un>.size))
            }
        }
        guard connected == 0 else { return nil }
        let sent = data.withUnsafeBytes { Darwin.send(descriptor, $0.baseAddress, $0.count, 0) }
        guard sent == data.count else { return nil }
        _ = Darwin.shutdown(descriptor, SHUT_WR)
        var response = Data(), buffer = [UInt8](repeating: 0, count: 1024)
        while response.count < 4096 {
            let count = buffer.withUnsafeMutableBytes {
                Darwin.read(descriptor, $0.baseAddress, $0.count)
            }
            if count <= 0 { break }
            response.append(contentsOf: buffer.prefix(count))
            if response.contains(0x0a) { break }
        }
        return try? JSONDecoder().decode(ControlResponse.self, from: response)
    }

    private func showError(_ message: String) {
        let alert = NSAlert()
        alert.messageText = "Não foi possível alterar o Wi-Fi"
        alert.informativeText = message
        alert.alertStyle = .warning
        alert.runModal()
    }
}

let app = NSApplication.shared
let delegate = AppDelegate()
app.delegate = delegate
app.run()
