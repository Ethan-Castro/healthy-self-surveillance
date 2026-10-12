import ApplicationServices
import AppKit
import Foundation
import ScreenCaptureKit

@MainActor
final class ScreenCaptureManager: ObservableObject {
    @Published var isEnabled = false
    @Published private(set) var isAuthorized = CGPreflightScreenCaptureAccess()

    func refreshAuthorization() {
        isAuthorized = CGPreflightScreenCaptureAccess()
    }

    func requestAuthorization() -> Bool {
        let granted = CGRequestScreenCaptureAccess()
        isAuthorized = granted
        return granted
    }

    func captureFrameBase64() async -> String? {
        guard isAuthorized else { return nil }
        guard let screenFrame = NSScreen.main?.frame else { return nil }
        guard #available(macOS 15.2, *) else { return nil }

        let image: CGImage? = await withCheckedContinuation { continuation in
            SCScreenshotManager.captureImage(in: screenFrame) { image, _ in
                continuation.resume(returning: image)
            }
        }

        guard let image else { return nil }
        let bitmap = NSBitmapImageRep(cgImage: image)
        let data = bitmap.representation(using: .jpeg, properties: [.compressionFactor: 0.58])
        return data?.base64EncodedString()
    }

    var latestFrameBase64: String? {
        nil
    }
}
