import AppKit
import Foundation

struct DesktopContextSnapshot {
    let app_name: String?
    let window_title: String?
    let system_idle_seconds: Int?
    let system_idle_state: String?
}

@MainActor
final class DesktopContextProvider {
    func snapshot() async -> DesktopContextSnapshot {
        let appName = NSWorkspace.shared.frontmostApplication?.localizedName
        let idleSeconds = Int(CGEventSource.secondsSinceLastEventType(.combinedSessionState, eventType: .null))
        let idleState = idleSeconds >= 60 ? "idle" : "active"
        let windowTitle = await currentWindowTitle()

        return DesktopContextSnapshot(
            app_name: appName,
            window_title: windowTitle,
            system_idle_seconds: idleSeconds,
            system_idle_state: idleState
        )
    }

    private func currentWindowTitle() async -> String? {
        await withCheckedContinuation { continuation in
            let process = Process()
            process.executableURL = URL(fileURLWithPath: "/usr/bin/osascript")
            process.arguments = [
                "-e",
                """
                tell application "System Events"
                  set frontWindowTitle to ""
                  try
                    set frontApp to first application process whose frontmost is true
                    try
                      if (count of windows of frontApp) > 0 then
                        set frontWindowTitle to name of front window of frontApp
                      end if
                    end try
                  end try
                  return frontWindowTitle
                end tell
                """,
            ]

            let pipe = Pipe()
            process.standardOutput = pipe
            process.terminationHandler = { _ in
                let data = pipe.fileHandleForReading.readDataToEndOfFile()
                let output = String(data: data, encoding: .utf8)?
                    .trimmingCharacters(in: .whitespacesAndNewlines)
                continuation.resume(returning: output?.isEmpty == true ? nil : output)
            }

            do {
                try process.run()
            } catch {
                continuation.resume(returning: nil)
            }
        }
    }
}
