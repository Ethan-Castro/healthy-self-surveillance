import Foundation

struct AppConfiguration {
    let apiBaseURL: URL
    let backendPort: Int
    let repoRoot: URL?
    let launchBackendInDebug: Bool
    let macOS26SDKRequiredMessage: String

    var liquidGlassPrerequisiteMessage: String {
        macOS26SDKRequiredMessage
    }

    static func load(bundle: Bundle = .main) -> AppConfiguration {
        let apiBaseURLString =
            (bundle.object(forInfoDictionaryKey: "FOCUS_BUDDY_API_BASE_URL") as? String) ??
            "http://127.0.0.1:8000"
        let backendPortString =
            (bundle.object(forInfoDictionaryKey: "FOCUS_BUDDY_BACKEND_PORT") as? String) ??
            "8000"
        let repoRootString = bundle.object(forInfoDictionaryKey: "FOCUS_BUDDY_REPO_ROOT") as? String
        let macOS26SDKRequiredMessage =
            "Running the native SwiftUI app with standard Apple materials on this Mac. True Liquid Glass upgrades later when the project moves to the macOS 26 SDK."

        return AppConfiguration(
            apiBaseURL: URL(string: apiBaseURLString) ?? URL(string: "http://127.0.0.1:8000")!,
            backendPort: Int(backendPortString) ?? 8000,
            repoRoot: repoRootString.map(URL.init(fileURLWithPath:)),
            launchBackendInDebug: true,
            macOS26SDKRequiredMessage: macOS26SDKRequiredMessage
        )
    }
}
