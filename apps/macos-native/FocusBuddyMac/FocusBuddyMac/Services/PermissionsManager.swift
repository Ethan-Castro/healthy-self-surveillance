import AVFoundation
import Foundation
@preconcurrency import UserNotifications

@MainActor
final class PermissionsManager: ObservableObject {
    @Published private(set) var cameraAuthorized = false
    @Published private(set) var microphoneAuthorized = false
    @Published private(set) var notificationsAuthorized = false
    @Published private(set) var screenCaptureAuthorized = false

    private let notificationCenter = UNUserNotificationCenter.current()
    private var notificationRefreshTask: Task<Void, Never>?

    deinit {
        notificationRefreshTask?.cancel()
    }

    func refresh() {
        cameraAuthorized = AVCaptureDevice.authorizationStatus(for: .video) == .authorized
        microphoneAuthorized = AVCaptureDevice.authorizationStatus(for: .audio) == .authorized
        screenCaptureAuthorized = CGPreflightScreenCaptureAccess()
        notificationRefreshTask?.cancel()

        let notificationCenter = notificationCenter
        notificationRefreshTask = Task { [weak self] in
            let settings = await notificationCenter.notificationSettings()
            guard !Task.isCancelled else { return }
            await MainActor.run {
                self?.notificationsAuthorized = settings.authorizationStatus == .authorized
            }
        }
    }

    func requestCamera() async -> Bool {
        let granted: Bool
        switch AVCaptureDevice.authorizationStatus(for: .video) {
        case .authorized:
            granted = true
        case .denied, .restricted:
            granted = false
        case .notDetermined:
            granted = await Self.requestMediaAccess(for: .video)
        @unknown default:
            granted = false
        }
        refresh()
        return granted
    }

    func requestMicrophone() async -> Bool {
        let granted: Bool
        switch AVCaptureDevice.authorizationStatus(for: .audio) {
        case .authorized:
            granted = true
        case .denied, .restricted:
            granted = false
        case .notDetermined:
            granted = await Self.requestMediaAccess(for: .audio)
        @unknown default:
            granted = false
        }
        refresh()
        return granted
    }

    func requestNotifications() async -> Bool {
        do {
            let granted = try await notificationCenter.requestAuthorization(options: [.alert, .badge, .sound])
            refresh()
            return granted
        } catch {
            refresh()
            return false
        }
    }

    func requestScreenCapture() -> Bool {
        let granted = CGRequestScreenCaptureAccess()
        refresh()
        return granted
    }

    func sendNotification(title: String, body: String) {
        guard notificationsAuthorized else { return }
        let content = UNMutableNotificationContent()
        content.title = title
        content.body = body
        content.sound = .default
        let request = UNNotificationRequest(identifier: UUID().uuidString, content: content, trigger: nil)
        notificationCenter.add(request, withCompletionHandler: nil)
    }

    nonisolated private static func requestMediaAccess(for mediaType: AVMediaType) async -> Bool {
        await withCheckedContinuation { continuation in
            AVCaptureDevice.requestAccess(for: mediaType) { granted in
                continuation.resume(returning: granted)
            }
        }
    }
}
