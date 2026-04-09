import Foundation

@MainActor
final class BackendManager: ObservableObject {
    enum State: Equatable {
        case idle
        case launching
        case connected
        case failed(String)
    }

    @Published private(set) var state: State = .idle
    @Published private(set) var logLines: [String] = []

    private let configuration: AppConfiguration
    private let apiClient: FocusBuddyAPIClient
    private var process: Process?
    private var stdoutPipe: Pipe?
    private var stderrPipe: Pipe?

    init(configuration: AppConfiguration, apiClient: FocusBuddyAPIClient) {
        self.configuration = configuration
        self.apiClient = apiClient
    }

    func ensureRunning() async {
        do {
            _ = try await apiClient.healthcheck()
            state = .connected
            appendLog("Connected to existing backend.")
            return
        } catch {
            appendLog("Backend health check failed. Attempting debug launch.")
        }

        guard configuration.launchBackendInDebug else {
            state = .failed("The local backend is unavailable and this build is not configured to auto-launch it.")
            return
        }

        do {
            try launchDebugBackendIfNeeded()
            try await waitUntilHealthy()
            state = .connected
            appendLog("Backend ready.")
        } catch {
            state = .failed(error.localizedDescription)
            appendLog("Backend launch failed: \(error.localizedDescription)")
        }
    }

    func stopBackend() {
        process?.terminate()
        process = nil
        stdoutPipe = nil
        stderrPipe = nil
    }

    private func launchDebugBackendIfNeeded() throws {
        guard process == nil else { return }
        guard let repoRoot = configuration.repoRoot else {
            throw NSError(
                domain: "FocusBuddyMac.BackendManager",
                code: 1,
                userInfo: [NSLocalizedDescriptionKey: "Repo root is missing. Set FOCUS_BUDDY_REPO_ROOT in the app target."]
            )
        }

        let serviceDirectory = repoRoot.appendingPathComponent("services/inference")
        guard FileManager.default.fileExists(atPath: serviceDirectory.path) else {
            throw NSError(
                domain: "FocusBuddyMac.BackendManager",
                code: 2,
                userInfo: [NSLocalizedDescriptionKey: "Cannot find services/inference at \(serviceDirectory.path)."]
            )
        }

        state = .launching

        let process = Process()
        process.executableURL = URL(fileURLWithPath: "/usr/bin/env")
        process.arguments = [
            "uv",
            "run",
            "uvicorn",
            "focus_catcher.api:app",
            "--app-dir",
            "src",
            "--port",
            String(configuration.backendPort),
        ]
        process.currentDirectoryURL = serviceDirectory

        let stdoutPipe = Pipe()
        let stderrPipe = Pipe()
        process.standardOutput = stdoutPipe
        process.standardError = stderrPipe

        stdoutPipe.fileHandleForReading.readabilityHandler = { [weak self] handle in
            let data = handle.availableData
            guard !data.isEmpty, let line = String(data: data, encoding: .utf8) else { return }
            Task { @MainActor in
                self?.appendLog(line.trimmingCharacters(in: .whitespacesAndNewlines))
            }
        }

        stderrPipe.fileHandleForReading.readabilityHandler = { [weak self] handle in
            let data = handle.availableData
            guard !data.isEmpty, let line = String(data: data, encoding: .utf8) else { return }
            Task { @MainActor in
                self?.appendLog(line.trimmingCharacters(in: .whitespacesAndNewlines))
            }
        }

        try process.run()
        appendLog("Launching backend with uvicorn on port \(configuration.backendPort).")

        process.terminationHandler = { [weak self] process in
            Task { @MainActor in
                self?.appendLog("Backend exited with status \(process.terminationStatus).")
                self?.process = nil
            }
        }

        self.process = process
        self.stdoutPipe = stdoutPipe
        self.stderrPipe = stderrPipe
    }

    private func waitUntilHealthy() async throws {
        for _ in 0..<60 {
            do {
                _ = try await apiClient.healthcheck()
                return
            } catch {
                try await Task.sleep(for: .milliseconds(500))
            }
        }
        throw NSError(
            domain: "FocusBuddyMac.BackendManager",
            code: 3,
            userInfo: [NSLocalizedDescriptionKey: "Timed out waiting for the backend to become healthy."]
        )
    }

    private func appendLog(_ line: String) {
        guard !line.isEmpty else { return }
        logLines.append(line)
        if logLines.count > 200 {
            logLines.removeFirst(logLines.count - 200)
        }
        print("[FocusBuddyMac] \(line)")
    }
}
