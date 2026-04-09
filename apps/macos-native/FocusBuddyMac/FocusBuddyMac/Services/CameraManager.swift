import AVFoundation
import AppKit
import Foundation
import ImageIO
import UniformTypeIdentifiers
import VideoToolbox

struct CameraSourceOption: Identifiable, Hashable {
    let id: String
    let displayName: String
    let captureSource: String
    let isPhoneCamera: Bool

    var menuLabel: String {
        isPhoneCamera ? "\(displayName) · iPhone" : displayName
    }

    var detailLabel: String {
        isPhoneCamera ? "Continuity Camera / iPhone source" : "Built-in or external Mac camera"
    }
}

@MainActor
final class CameraManager: NSObject, ObservableObject {
    @Published private(set) var isRunning = false
    @Published private(set) var latestFrameBase64: String?
    @Published private(set) var latestImage: NSImage?
    @Published private(set) var availableSources: [CameraSourceOption] = []
    @Published private(set) var selectedSourceID: String = ""

    let session = AVCaptureSession()

    private let captureQueue = DispatchQueue(label: "FocusBuddyMac.CameraCaptureQueue")
    private var output = AVCaptureVideoDataOutput()
    nonisolated private let emissionState = SampleEmissionState()

    override init() {
        super.init()
        refreshAvailableSources()
    }

    var selectedSource: CameraSourceOption? {
        availableSources.first(where: { $0.id == selectedSourceID })
    }

    func refreshAvailableSources() {
        let devices = Self.discoveredDevices()
        let nextSources = devices.map(Self.makeSourceOption)
        availableSources = nextSources

        if nextSources.contains(where: { $0.id == selectedSourceID }) {
            return
        }

        if let preferredPhone = nextSources.first(where: \.isPhoneCamera) {
            selectedSourceID = preferredPhone.id
        } else if let defaultDevice = AVCaptureDevice.default(for: .video),
                  let matchingDefault = nextSources.first(where: { $0.id == defaultDevice.uniqueID }) {
            selectedSourceID = matchingDefault.id
        } else {
            selectedSourceID = nextSources.first?.id ?? ""
        }
    }

    func selectSource(id: String) {
        guard availableSources.contains(where: { $0.id == id }) else { return }
        selectedSourceID = id
    }

    func start() async throws {
        guard !isRunning else { return }
        refreshAvailableSources()

        session.beginConfiguration()
        session.sessionPreset = .high
        session.inputs.forEach { session.removeInput($0) }
        session.outputs.forEach { session.removeOutput($0) }

        guard let device = selectedCaptureDevice() ?? AVCaptureDevice.default(for: .video) else {
            session.commitConfiguration()
            throw NSError(
                domain: "FocusBuddyMac.CameraManager",
                code: 1,
                userInfo: [NSLocalizedDescriptionKey: "No camera device is available."]
            )
        }

        let input = try AVCaptureDeviceInput(device: device)
        guard session.canAddInput(input) else {
            session.commitConfiguration()
            throw NSError(
                domain: "FocusBuddyMac.CameraManager",
                code: 2,
                userInfo: [NSLocalizedDescriptionKey: "The camera input could not be added to the capture session."]
            )
        }
        session.addInput(input)

        output = AVCaptureVideoDataOutput()
        output.alwaysDiscardsLateVideoFrames = true
        output.videoSettings = [
            kCVPixelBufferPixelFormatTypeKey as String: Int(kCVPixelFormatType_32BGRA)
        ]
        output.setSampleBufferDelegate(self, queue: captureQueue)

        guard session.canAddOutput(output) else {
            session.commitConfiguration()
            throw NSError(
                domain: "FocusBuddyMac.CameraManager",
                code: 3,
                userInfo: [NSLocalizedDescriptionKey: "The camera output could not be added to the capture session."]
            )
        }
        session.addOutput(output)
        session.commitConfiguration()

        session.startRunning()
        isRunning = true
    }

    func stop() {
        guard isRunning else { return }
        output.setSampleBufferDelegate(nil, queue: nil)
        session.stopRunning()
        isRunning = false
        latestFrameBase64 = nil
        latestImage = nil
    }

    private func selectedCaptureDevice() -> AVCaptureDevice? {
        let devices = Self.discoveredDevices()
        return devices.first(where: { $0.uniqueID == selectedSourceID })
    }

    private static func discoveredDevices() -> [AVCaptureDevice] {
        let discovery = AVCaptureDevice.DiscoverySession(
            deviceTypes: supportedDeviceTypes(),
            mediaType: .video,
            position: .unspecified
        )
        if !discovery.devices.isEmpty {
            return discovery.devices
        }
        if let defaultDevice = AVCaptureDevice.default(for: .video) {
            return [defaultDevice]
        }
        return []
    }

    private static func supportedDeviceTypes() -> [AVCaptureDevice.DeviceType] {
        return [
            .builtInWideAngleCamera,
            .external,
            .continuityCamera,
        ]
    }

    private static func makeSourceOption(device: AVCaptureDevice) -> CameraSourceOption {
        let loweredName = device.localizedName.lowercased()
        let loweredType = device.deviceType.rawValue.lowercased()
        let isPhoneCamera =
            loweredName.contains("iphone") ||
            loweredType.contains("continuity")
        return CameraSourceOption(
            id: device.uniqueID,
            displayName: device.localizedName,
            captureSource: isPhoneCamera ? "iphone_camera" : "mac_camera",
            isPhoneCamera: isPhoneCamera
        )
    }
}

private final class SampleEmissionState: @unchecked Sendable {
    var lastEmissionUptime: TimeInterval = 0
}

extension CameraManager: AVCaptureVideoDataOutputSampleBufferDelegate {
    nonisolated func captureOutput(
        _ output: AVCaptureOutput,
        didOutput sampleBuffer: CMSampleBuffer,
        from connection: AVCaptureConnection
    ) {
        let now = ProcessInfo.processInfo.systemUptime
        guard now - emissionState.lastEmissionUptime >= 0.4 else { return }
        emissionState.lastEmissionUptime = now

        guard let pixelBuffer = CMSampleBufferGetImageBuffer(sampleBuffer) else { return }

        var cgImage: CGImage?
        let status = VTCreateCGImageFromCVPixelBuffer(pixelBuffer, options: nil, imageOut: &cgImage)
        guard status == noErr, let cgImage else { return }

        let jpegData = Self.encodeJPEG(from: cgImage)
        let base64 = jpegData?.base64EncodedString()

        Task { @MainActor [weak self] in
            if let jpegData {
                self?.latestImage = NSImage(data: jpegData)
            } else {
                self?.latestImage = nil
            }
            self?.latestFrameBase64 = base64
        }
    }

    nonisolated private static func encodeJPEG(from image: CGImage) -> Data? {
        let mutableData = NSMutableData()
        guard
            let destination = CGImageDestinationCreateWithData(
                mutableData,
                UTType.jpeg.identifier as CFString,
                1,
                nil
            )
        else {
            return nil
        }

        let properties: CFDictionary = [
            kCGImageDestinationLossyCompressionQuality: 0.72
        ] as CFDictionary

        CGImageDestinationAddImage(destination, image, properties)
        guard CGImageDestinationFinalize(destination) else { return nil }
        return mutableData as Data
    }
}
