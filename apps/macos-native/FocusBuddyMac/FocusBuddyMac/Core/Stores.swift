import Combine
import Foundation

@MainActor
final class PreferencesStore: ObservableObject {
    @Published var draft: AnalyticsPreferences = .fallback
    @Published private(set) var saved: AnalyticsPreferences = .fallback
    @Published private(set) var isLoading = false
    @Published var errorMessage: String?

    private let apiClient: FocusBuddyAPIClient

    init(apiClient: FocusBuddyAPIClient) {
        self.apiClient = apiClient
    }

    func load() async {
        isLoading = true
        defer { isLoading = false }

        do {
            let preferences = try await apiClient.fetchPreferences()
            draft = preferences
            saved = preferences
            errorMessage = nil
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func save() async {
        isLoading = true
        defer { isLoading = false }

        do {
            let updated = try await apiClient.updatePreferences(draft)
            draft = updated
            saved = updated
            errorMessage = nil
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    var isDirty: Bool {
        draft != saved
    }
}

@MainActor
final class AnalyticsStore: ObservableObject {
    @Published private(set) var today: DayAnalyticsView?
    @Published private(set) var week: WeekAnalyticsView?
    @Published private(set) var experiments: ExperimentComparisonView?
    @Published private(set) var insights: [InsightCard] = []
    @Published var errorMessage: String?

    private let apiClient: FocusBuddyAPIClient

    init(apiClient: FocusBuddyAPIClient) {
        self.apiClient = apiClient
    }

    func refresh() async {
        do {
            self.today = try await apiClient.fetchTodayAnalytics()
            self.week = try await apiClient.fetchWeekAnalytics()
            self.experiments = try await apiClient.fetchExperimentAnalytics()
            self.insights = try await apiClient.fetchAnalyticsInsights()
            errorMessage = nil
        } catch {
            errorMessage = error.localizedDescription
        }
    }
}

@MainActor
final class ReviewStore: ObservableObject {
    @Published private(set) var sessions: [SessionSnapshot] = []
    @Published var selectedSessionID: String?
    @Published private(set) var reviewDetail: SessionReviewDetail?
    @Published private(set) var analyticsDetail: SessionAnalyticsDetail?
    @Published var errorMessage: String?

    private let apiClient: FocusBuddyAPIClient

    init(apiClient: FocusBuddyAPIClient) {
        self.apiClient = apiClient
    }

    func refreshLibrary(preferredID: String? = nil) async {
        do {
            let nextSessions = try await apiClient.listSessions()
                .filter { $0.summary.total_reviews > 0 }
            sessions = nextSessions
            let nextSelectedID = preferredID ?? selectedSessionID ?? nextSessions.first?.session_id
            selectedSessionID = nextSelectedID
            errorMessage = nil
            if let nextSelectedID {
                await loadSession(id: nextSelectedID)
            } else {
                reviewDetail = nil
                analyticsDetail = nil
            }
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func loadSession(id: String) async {
        do {
            reviewDetail = try await apiClient.fetchSessionReview(id: id)
            analyticsDetail = try await apiClient.fetchSessionAnalytics(id: id)
            selectedSessionID = id
            errorMessage = nil
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func markSelectedSessionRemarkable(note: String?) async {
        guard let selectedSessionID else { return }
        do {
            let updated = try await apiClient.markSessionRemarkable(
                id: selectedSessionID,
                request: RemarkableRequest(remarkable: true, note: note)
            )
            await refreshLibrary(preferredID: updated.session_id)
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func markMoment(sequence: Int, note: String?) async {
        guard let selectedSessionID else { return }
        do {
            _ = try await apiClient.markMomentRemarkable(
                id: selectedSessionID,
                sequence: sequence,
                request: RemarkableRequest(remarkable: true, note: note)
            )
            await loadSession(id: selectedSessionID)
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func clearMoment(sequence: Int) async {
        guard let selectedSessionID else { return }
        do {
            _ = try await apiClient.clearMomentRemarkable(id: selectedSessionID, sequence: sequence)
            await loadSession(id: selectedSessionID)
        } catch {
            errorMessage = error.localizedDescription
        }
    }
}

@MainActor
final class SessionStore: ObservableObject {
    @Published private(set) var setup: SetupStatus?
    @Published private(set) var session: SessionSnapshot?
    @Published private(set) var isCameraEnabled = false
    @Published var busyMessage: String?
    @Published var errorMessage: String?

    @Published var sessionName = UserDefaults.standard.string(forKey: "FocusBuddyMac.sessionName") ?? SessionConfig.default.session_name {
        didSet {
            UserDefaults.standard.set(sessionName, forKey: "FocusBuddyMac.sessionName")
        }
    }
    @Published var includeScreenAnalysis = UserDefaults.standard.bool(forKey: "FocusBuddyMac.includeScreenAnalysis") {
        didSet {
            UserDefaults.standard.set(includeScreenAnalysis, forKey: "FocusBuddyMac.includeScreenAnalysis")
        }
    }
    @Published var runtimeProfile: RuntimeProfile = RuntimeProfile(
        rawValue: UserDefaults.standard.string(forKey: "FocusBuddyMac.runtimeProfile") ?? ""
    ) ?? .standard {
        didSet {
            UserDefaults.standard.set(runtimeProfile.rawValue, forKey: "FocusBuddyMac.runtimeProfile")
        }
    }
    @Published var analysisMode: AnalysisMode = AnalysisMode(
        rawValue: UserDefaults.standard.string(forKey: "FocusBuddyMac.analysisMode") ?? ""
    ) ?? .annotation {
        didSet {
            UserDefaults.standard.set(analysisMode.rawValue, forKey: "FocusBuddyMac.analysisMode")
        }
    }
    @Published var liveCoachingMode: LiveCoachingMode = LiveCoachingMode(
        rawValue: UserDefaults.standard.string(forKey: "FocusBuddyMac.liveCoachingMode") ?? ""
    ) ?? .notifications {
        didSet {
            UserDefaults.standard.set(liveCoachingMode.rawValue, forKey: "FocusBuddyMac.liveCoachingMode")
        }
    }
    @Published var captureToggles: DataSourceToggles = .default
    @Published var manualTags: ManualTags = .empty
    @Published var showOrb = UserDefaults.standard.object(forKey: "FocusBuddyMac.showOrb") as? Bool ?? true {
        didSet {
            UserDefaults.standard.set(showOrb, forKey: "FocusBuddyMac.showOrb")
        }
    }
    @Published var desktopNudgesEnabled = UserDefaults.standard.object(forKey: "FocusBuddyMac.desktopNudges") as? Bool ?? true {
        didSet {
            UserDefaults.standard.set(desktopNudgesEnabled, forKey: "FocusBuddyMac.desktopNudges")
        }
    }

    private let apiClient: FocusBuddyAPIClient
    private let cameraManager: CameraManager
    private let screenCaptureManager: ScreenCaptureManager
    private let desktopContextProvider: DesktopContextProvider
    private let permissionsManager: PermissionsManager

    private var reviewLoopTask: Task<Void, Never>?
    private var frameSequence = 0
    private var lastReviewAt = Date.distantPast
    private var lastPollAt = Date.distantPast
    private var lastNotificationKey: String?

    init(
        apiClient: FocusBuddyAPIClient,
        cameraManager: CameraManager,
        screenCaptureManager: ScreenCaptureManager,
        desktopContextProvider: DesktopContextProvider,
        permissionsManager: PermissionsManager
    ) {
        self.apiClient = apiClient
        self.cameraManager = cameraManager
        self.screenCaptureManager = screenCaptureManager
        self.desktopContextProvider = desktopContextProvider
        self.permissionsManager = permissionsManager
    }

    func applyDefaultPreferences(_ preferences: AnalyticsPreferences) {
        liveCoachingMode = preferences.live_coaching_mode
        captureToggles = preferences.capture_toggles
        captureToggles.camera = true
        manualTags = preferences.default_manual_tags
    }

    var availableCameraSources: [CameraSourceOption] {
        cameraManager.availableSources
    }

    var selectedCameraSourceID: String {
        cameraManager.selectedSource?.id ?? ""
    }

    var selectedCameraSource: CameraSourceOption? {
        cameraManager.selectedSource
    }

    func refreshCameraSources() {
        cameraManager.refreshAvailableSources()
    }

    func refreshSetup() async {
        do {
            setup = try await apiClient.fetchSetup()
            errorMessage = nil
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func enableCamera() async {
        guard await permissionsManager.requestCamera() else {
            errorMessage = "Camera permission was denied."
            return
        }

        do {
            try await cameraManager.start()
            isCameraEnabled = true
            errorMessage = nil
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func stopCamera() {
        cameraManager.stop()
        isCameraEnabled = false
    }

    func selectCameraSource(_ id: String) async {
        cameraManager.selectSource(id: id)
        guard isCameraEnabled else { return }

        do {
            cameraManager.stop()
            try await cameraManager.start()
            isCameraEnabled = true
            errorMessage = nil
        } catch {
            isCameraEnabled = false
            errorMessage = error.localizedDescription
        }
    }

    func requestScreenCapture() {
        if screenCaptureManager.requestAuthorization() {
            screenCaptureManager.isEnabled = true
            errorMessage = nil
        } else {
            errorMessage = "Screen capture permission was denied."
        }
    }

    var startBlocker: String? {
        if setup?.ready != true {
            return setup?.message ?? "Model is not ready yet."
        }
        if !isCameraEnabled {
            return "Enable the camera before starting a live session."
        }
        if includeScreenAnalysis && !screenCaptureManager.isAuthorized {
            return "Grant screen capture access or turn screen analysis off."
        }
        return nil
    }

    func startOrResumeSession() async {
        guard startBlocker == nil else {
            errorMessage = startBlocker
            return
        }

        busyMessage = "Starting session"
        defer { busyMessage = nil }

        do {
            if let session, session.status == .paused {
                let resumed = try await apiClient.transitionSession(id: session.session_id, action: "start")
                handleUpdatedSession(resumed)
                startReviewLoop()
                errorMessage = nil
                return
            }

            let created = try await apiClient.createSession(config: buildSessionConfig())
            let started = try await apiClient.transitionSession(id: created.session_id, action: "start")
            frameSequence = 0
            lastReviewAt = .distantPast
            handleUpdatedSession(started)
            await submitContext(reason: .start)
            startReviewLoop()
            errorMessage = nil
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func pauseSession() async {
        guard let session else { return }
        busyMessage = "Pausing session"
        defer { busyMessage = nil }

        do {
            let paused = try await apiClient.transitionSession(id: session.session_id, action: "pause")
            handleUpdatedSession(paused)
            reviewLoopTask?.cancel()
            errorMessage = nil
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func stopSession() async {
        guard let session else { return }
        busyMessage = "Ending session"
        defer { busyMessage = nil }

        do {
            await submitContext(reason: .stop)
            let stopped = try await apiClient.transitionSession(id: session.session_id, action: "stop")
            handleUpdatedSession(stopped)
            reviewLoopTask?.cancel()
            stopCamera()
            errorMessage = nil
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func saveSession() async {
        guard let session else { return }
        busyMessage = "Saving session"
        defer { busyMessage = nil }

        do {
            let saved = try await apiClient.saveSession(id: session.session_id)
            handleUpdatedSession(saved)
            errorMessage = nil
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func runRescan() async {
        guard let session else { return }
        busyMessage = "Running rescan"
        defer { busyMessage = nil }

        do {
            _ = try await apiClient.rescanSession(id: session.session_id)
            let refreshed = try await apiClient.fetchSession(id: session.session_id)
            handleUpdatedSession(refreshed)
            errorMessage = nil
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    private func buildSessionConfig() -> SessionConfig {
        var toggles = captureToggles
        toggles.camera = true
        toggles.screen = includeScreenAnalysis && screenCaptureManager.isAuthorized

        return SessionConfig(
            session_name: sessionName.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty ? SessionConfig.default.session_name : sessionName,
            include_screen_analysis: toggles.screen,
            runtime_profile: runtimeProfile,
            analysis_mode: analysisMode,
            live_coaching_mode: liveCoachingMode,
            capture_toggles: toggles,
            manual_tags: manualTags,
            focused_review_cadence_ms: SessionConfig.default.focused_review_cadence_ms,
            active_review_cadence_ms: SessionConfig.default.active_review_cadence_ms,
            timelapse_capture_interval_reviews: SessionConfig.default.timelapse_capture_interval_reviews,
            temporary_review_window_sec: SessionConfig.default.temporary_review_window_sec
        )
    }

    private func startReviewLoop() {
        reviewLoopTask?.cancel()
        reviewLoopTask = Task { [weak self] in
            guard let self else { return }
            while !Task.isCancelled {
                await self.tick()
                try? await Task.sleep(nanoseconds: 250_000_000)
            }
        }
    }

    private func tick() async {
        guard let session else { return }
        guard session.status == .running else { return }

        let now = Date()
        let cadenceMilliseconds = (session.current_label == .drifting || session.current_label == .distracted) ? 650 : 1_200
        let reviewDue = now.timeIntervalSince(lastReviewAt) >= Double(cadenceMilliseconds) / 1_000.0
        let pollDue = now.timeIntervalSince(lastPollAt) >= 1.0

        if reviewDue {
            await submitLiveReview(force: lastReviewAt == .distantPast)
            lastReviewAt = Date()
            return
        }

        if pollDue, let currentSessionID = self.session?.session_id {
            do {
                let refreshed = try await apiClient.fetchSession(id: currentSessionID)
                handleUpdatedSession(refreshed)
                lastPollAt = Date()
            } catch {
                errorMessage = error.localizedDescription
            }
        }
    }

    private func submitLiveReview(force: Bool) async {
        guard let session else { return }
        guard let cameraImage = cameraManager.latestFrameBase64 else { return }
        let screenImage: String?
        if includeScreenAnalysis && screenCaptureManager.isAuthorized {
            screenImage = await screenCaptureManager.captureFrameBase64()
        } else {
            screenImage = nil
        }

        frameSequence += 1
        let reviewInput = ReviewInput(
            frame_sequence: frameSequence,
            camera_image_b64: cameraImage,
            screen_image_b64: screenImage,
            include_screen_analysis: includeScreenAnalysis && screenCaptureManager.isAuthorized,
            device_id: selectedCameraSource?.isPhoneCamera == true ? "iphone" : "mac",
            capture_source: selectedCameraSource?.captureSource ?? "mac_camera",
            force_review: force
        )

        do {
            let updated = try await apiClient.submitReview(id: session.session_id, review: reviewInput)
            handleUpdatedSession(updated)
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func submitContext(reason: ContextCaptureReason) async {
        guard let session else { return }
        let toggles = session.capture_toggles
        guard toggles.app_context || toggles.input_activity || toggles.location || toggles.manual_tags else {
            return
        }

        let desktop = await desktopContextProvider.snapshot()
        let payload = ContextCaptureRequest(
            reason: reason,
            device_id: "mac",
            capture_source: selectedCameraSource?.captureSource ?? (includeScreenAnalysis ? "mac_screen" : "mac_camera"),
            context_source: "mac",
            screen_enabled: includeScreenAnalysis,
            app_name: desktop.app_name,
            window_title: desktop.window_title,
            app_category: nil,
            system_idle_seconds: desktop.system_idle_seconds,
            system_idle_state: desktop.system_idle_state,
            keyboard_events: 0,
            mouse_events: 0,
            scroll_events: 0,
            sound_rms: nil,
            sound_peak: nil,
            sound_bucket: nil,
            location_label: manualTags.location_label,
            calendar_title: nil,
            calendar_category: nil,
            manual_tags: manualTags,
            phone_present: manualTags.phone_present
        )

        do {
            let updated = try await apiClient.submitContext(id: session.session_id, context: payload)
            handleUpdatedSession(updated)
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    private func handleUpdatedSession(_ nextSession: SessionSnapshot) {
        session = nextSession
        maybeSendNotification(for: nextSession)
    }

    private func maybeSendNotification(for session: SessionSnapshot) {
        guard desktopNudgesEnabled else { return }
        guard session.status == .running else { return }

        let shouldNotify =
            session.current_label == .away ||
            session.current_label == .distracted ||
            session.companion_message.hasPrefix("Quick reset:") ||
            session.companion_message.hasPrefix("Tiny reset:")

        guard shouldNotify else { return }

        let notificationKey = "\(session.session_id):\(session.last_review_at ?? "none"):\(session.current_label.rawValue):\(session.companion_message)"
        guard notificationKey != lastNotificationKey else { return }
        lastNotificationKey = notificationKey

        permissionsManager.sendNotification(
            title: "Focus Buddy: \(displayLabel(for: session.current_label, analysisMode: session.analysis_mode))",
            body: "\(visibleReason(for: session.current_label, reason: session.short_reason, analysisMode: session.analysis_mode)) \(session.companion_message)".trimmingCharacters(in: .whitespaces)
        )
    }

    func displayLabel(for label: FocusLabel, analysisMode: AnalysisMode) -> String {
        if analysisMode == .classification {
            return label == .focused ? "Focused" : "Unfocused"
        }
        return label.title
    }

    func visibleReason(for label: FocusLabel, reason: String, analysisMode: AnalysisMode) -> String {
        if analysisMode == .classification {
            switch label {
            case .focused:
                return "Staying on task."
            case .drifting:
                return "Attention is slipping. Bring your eyes back to the work."
            case .distracted:
                return "Attention is clearly off task. Reset to one thing."
            case .away:
                return "You appear to be away from the task right now."
            }
        }
        return reason
    }

    var orbState: OrbDisplayState {
        guard let session else {
            return OrbDisplayState()
        }
        return OrbDisplayState(
            label: session.current_label,
            analysis_mode: session.analysis_mode,
            reason: visibleReason(for: session.current_label, reason: session.short_reason, analysisMode: session.analysis_mode),
            message: session.companion_message,
            is_active: session.status == .running
        )
    }
}

@MainActor
final class AppModel: ObservableObject {
    @Published var selectedTab: NavigationTab = {
        let stored = UserDefaults.standard.string(forKey: "FocusBuddyMac.selectedTab")
        switch stored {
        case "stats", "patterns":
            return .insights
        default:
            return NavigationTab(rawValue: stored ?? "") ?? .live
        }
    }()

    let configuration: AppConfiguration
    let apiClient: FocusBuddyAPIClient
    let backendManager: BackendManager
    let permissionsManager: PermissionsManager
    let cameraManager: CameraManager
    let screenCaptureManager: ScreenCaptureManager
    let desktopContextProvider: DesktopContextProvider
    let preferencesStore: PreferencesStore
    let analyticsStore: AnalyticsStore
    let reviewStore: ReviewStore
    let sessionStore: SessionStore
    let orbPanelController: OrbPanelController

    @Published private(set) var globalError: String?

    private var hasStarted = false
    private var cancellables = Set<AnyCancellable>()

    init() {
        configuration = AppConfiguration.load()
        apiClient = FocusBuddyAPIClient(baseURL: configuration.apiBaseURL)
        permissionsManager = PermissionsManager()
        cameraManager = CameraManager()
        screenCaptureManager = ScreenCaptureManager()
        desktopContextProvider = DesktopContextProvider()
        backendManager = BackendManager(configuration: configuration, apiClient: apiClient)
        preferencesStore = PreferencesStore(apiClient: apiClient)
        analyticsStore = AnalyticsStore(apiClient: apiClient)
        reviewStore = ReviewStore(apiClient: apiClient)
        sessionStore = SessionStore(
            apiClient: apiClient,
            cameraManager: cameraManager,
            screenCaptureManager: screenCaptureManager,
            desktopContextProvider: desktopContextProvider,
            permissionsManager: permissionsManager
        )
        orbPanelController = OrbPanelController()

        sessionStore.$showOrb
            .sink { [weak self] enabled in
                self?.orbPanelController.setEnabled(enabled)
            }
            .store(in: &cancellables)

        sessionStore.$session
            .sink { [weak self] session in
                self?.orbPanelController.update(state: self?.sessionStore.orbState ?? OrbDisplayState())
                guard let self, let session else { return }
                Task {
                    await self.reviewStore.refreshLibrary(preferredID: session.session_id)
                    await self.analyticsStore.refresh()
                }
            }
            .store(in: &cancellables)

        preferencesStore.$draft
            .sink { [weak self] preferences in
                self?.sessionStore.applyDefaultPreferences(preferences)
            }
            .store(in: &cancellables)

        $selectedTab
            .sink { value in
                UserDefaults.standard.set(value.rawValue, forKey: "FocusBuddyMac.selectedTab")
            }
            .store(in: &cancellables)
    }

    func start() async {
        guard !hasStarted else { return }
        hasStarted = true
        permissionsManager.refresh()
        orbPanelController.setEnabled(sessionStore.showOrb)
        orbPanelController.update(state: sessionStore.orbState)

        await backendManager.ensureRunning()
        switch backendManager.state {
        case .failed(let message):
            globalError = message
        default:
            globalError = nil
        }

        await sessionStore.refreshSetup()
        await preferencesStore.load()
        await analyticsStore.refresh()
        await reviewStore.refreshLibrary()
    }
}
