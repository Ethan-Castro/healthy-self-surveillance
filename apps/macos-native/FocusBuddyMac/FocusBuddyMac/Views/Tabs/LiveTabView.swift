import SwiftUI

struct LiveTabView: View {
    @ObservedObject var sessionStore: SessionStore
    @ObservedObject var permissionsManager: PermissionsManager
    @ObservedObject var cameraManager: CameraManager
    @ObservedObject var backendManager: BackendManager
    let liquidGlassMessage: String

    private var currentSession: SessionSnapshot? { sessionStore.session }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 24) {
                heroSection

                if let errorMessage = sessionStore.errorMessage {
                    GlassBanner(title: "Live session issue", message: errorMessage, tone: .critical)
                }

                if let blocker = sessionStore.startBlocker, currentSession?.status != .running {
                    GlassBanner(title: "Before you start", message: blocker, tone: .caution)
                }

                cameraSection
                companionSection
                activitySection
            }
            .padding(.horizontal, 28)
            .padding(.top, 24)
            .padding(.bottom, 116)
        }
        .scrollIndicators(.hidden)
    }

    private var heroSection: some View {
        GlassSection(title: "Live", subtitle: "One calm surface for the current session. Modes and privacy defaults now live in Settings.") {
            VStack(alignment: .leading, spacing: 20) {
                HStack(alignment: .top, spacing: 24) {
                    VStack(alignment: .leading, spacing: 12) {
                        HStack(spacing: 10) {
                            StatusChip(label: liveDisplayTitle, tone: liveTone)
                            StatusChip(label: sessionStatusTitle, tone: sessionStatusTone)
                            if let modelName = sessionStore.setup?.model_name, sessionStore.setup?.ready == true {
                                StatusChip(label: modelName, tone: .good)
                            }
                        }

                        Text(liveReason)
                            .font(.system(size: 30, weight: .bold, design: .rounded))
                            .foregroundStyle(Color.primary.opacity(0.88))

                        Text(companionMessage)
                            .font(.subheadline)
                            .foregroundStyle(.secondary)
                            .frame(maxWidth: 620, alignment: .leading)
                    }

                    Spacer(minLength: 24)

                    VStack(alignment: .leading, spacing: 10) {
                        Text("Session defaults")
                            .font(.headline)
                        Text(sessionDefaultsLine)
                            .font(.caption)
                            .foregroundStyle(.secondary)
                        Text(liquidGlassMessage)
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
                    .frame(maxWidth: 260, alignment: .leading)
                }

                TextField("Session name", text: $sessionStore.sessionName)
                    .textFieldStyle(.roundedBorder)

                HStack(spacing: 16) {
                    MetricTile(title: "Session", value: sessionStatusTitle, footnote: statusFootnote)
                    MetricTile(title: "Focus ratio", value: focusRatioValue)
                    MetricTile(title: "Reviews", value: reviewCountValue)
                    MetricTile(title: "Keyframes", value: keyframeCountValue)
                }

                HStack(spacing: 12) {
                    Button(primaryActionTitle) {
                        Task { await sessionStore.startOrResumeSession() }
                    }
                    .buttonStyle(.borderedProminent)
                    .disabled(sessionStore.startBlocker != nil)

                    Button("Pause") {
                        Task { await sessionStore.pauseSession() }
                    }
                    .buttonStyle(.bordered)
                    .disabled(currentSession?.status != .running)

                    Button("End") {
                        Task { await sessionStore.stopSession() }
                    }
                    .buttonStyle(.bordered)
                    .disabled(currentSession == nil || currentSession?.status == .stopped)

                    Button("Save") {
                        Task { await sessionStore.saveSession() }
                    }
                    .buttonStyle(.bordered)
                    .disabled(currentSession?.status != .stopped)

                    Button("Rescan") {
                        Task { await sessionStore.runRescan() }
                    }
                    .buttonStyle(.bordered)
                    .disabled(currentSession?.can_rescan != true)
                }
            }
        }
    }

    private var cameraSection: some View {
        GlassSection(title: "Camera", subtitle: "Choose the source, turn it on, and keep the preview honest.") {
            VStack(alignment: .leading, spacing: 18) {
                HStack(alignment: .top, spacing: 16) {
                    VStack(alignment: .leading, spacing: 8) {
                        Text("Camera source")
                            .font(.caption)
                            .foregroundStyle(.secondary)

                        Picker("Camera source", selection: cameraSourceBinding) {
                            ForEach(sessionStore.availableCameraSources) { source in
                                Text(source.menuLabel).tag(source.id)
                            }
                        }
                        .pickerStyle(.menu)
                        .frame(maxWidth: 280, alignment: .leading)

                        if let selectedSource = sessionStore.selectedCameraSource {
                            Text(selectedSource.detailLabel)
                                .font(.caption)
                                .foregroundStyle(.secondary)
                        } else {
                            Text("No camera sources detected yet.")
                                .font(.caption)
                                .foregroundStyle(.secondary)
                        }
                    }

                    Spacer()

                    HStack(spacing: 12) {
                        Button("Refresh cameras") {
                            sessionStore.refreshCameraSources()
                        }
                        .buttonStyle(.bordered)

                        Button(sessionStore.isCameraEnabled ? "Refresh preview" : "Enable camera") {
                            Task { await sessionStore.enableCamera() }
                        }
                        .buttonStyle(.borderedProminent)

                        if sessionStore.isCameraEnabled {
                            Button("Turn off") {
                                sessionStore.stopCamera()
                            }
                            .buttonStyle(.bordered)
                        }
                    }
                }

                CameraPreviewView(image: cameraManager.latestImage, isLive: cameraManager.isRunning)
            }
        }
    }

    private var companionSection: some View {
        GlassSection(title: "Companion", subtitle: "The orb and native nudges live outside the main window so the app can stay quiet.") {
            HStack(alignment: .top, spacing: 24) {
                VStack(alignment: .leading, spacing: 12) {
                    HStack(spacing: 10) {
                        StatusChip(label: sessionStore.orbState.display_title, tone: sessionStore.orbState.label.tone)
                        StatusChip(label: sessionStore.orbState.is_active ? "Active" : "Idle", tone: sessionStore.orbState.is_active ? .good : .neutral)
                    }

                    Text(sessionStore.orbState.reason)
                        .font(.headline)
                    Text(sessionStore.orbState.message)
                        .font(.subheadline)
                        .foregroundStyle(.secondary)
                        .frame(maxWidth: 560, alignment: .leading)
                }

                Spacer(minLength: 24)

                VStack(alignment: .leading, spacing: 12) {
                    Toggle("Show floating orb", isOn: $sessionStore.showOrb)
                    Toggle("Desktop nudges", isOn: $sessionStore.desktopNudgesEnabled)

                    if let source = sessionStore.selectedCameraSource, source.isPhoneCamera {
                        Text("iPhone camera mode is active. Focus Buddy will treat the phone as the companion camera, not as a distraction.")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                            .frame(maxWidth: 260, alignment: .leading)
                    }
                }
                .frame(maxWidth: 280, alignment: .leading)
            }
        }
    }

    private var activitySection: some View {
        GlassSection(title: "Session pulse", subtitle: "A quick look at the current session instead of a wall of controls.") {
            VStack(alignment: .leading, spacing: 18) {
                HStack(spacing: 16) {
                    MetricTile(title: "Focused", value: focusedCountValue)
                    MetricTile(title: "Distracted", value: distractedCountValue)
                    MetricTile(title: "Away", value: awayCountValue)
                    MetricTile(title: "Last review", value: DisplayFormat.timestamp(currentSession?.last_review_at))
                }

                if let currentSession, !currentSession.recent_reviews.isEmpty {
                    VStack(spacing: 12) {
                        ForEach(Array(currentSession.recent_reviews.suffix(4).reversed())) { review in
                            reviewCard(review, analysisMode: currentSession.analysis_mode)
                        }
                    }
                } else {
                    EmptyStateCard(
                        title: "No live moments yet",
                        message: "Once a session is running, the newest Gemma-backed moments will appear here."
                    )
                }
            }
        }
    }

    private func reviewCard(_ review: ReviewEntry, analysisMode: AnalysisMode) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                Text(sessionStore.displayLabel(for: review.label, analysisMode: analysisMode))
                    .font(.headline)
                Spacer()
                Text(DisplayFormat.timestamp(review.timestamp))
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }

            Text(review.note)
                .font(.subheadline)

            Text(review.buddy_note)
                .font(.caption)
                .foregroundStyle(.secondary)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(16)
        .background(Color.white.opacity(0.35), in: RoundedRectangle(cornerRadius: 22, style: .continuous))
    }

    private var primaryActionTitle: String {
        currentSession?.status == .paused ? "Resume" : "Start"
    }

    private var sessionStatusTitle: String {
        if let currentSession {
            return currentSession.status.rawValue.capitalized
        }
        return sessionStore.setup?.ready == true ? "Ready" : "Waiting"
    }

    private var statusFootnote: String {
        if let currentSession {
            return "Last review \(DisplayFormat.timestamp(currentSession.last_review_at))"
        }
        return backendManager.state.title
    }

    private var liveDisplayTitle: String {
        if let currentSession {
            return sessionStore.displayLabel(for: currentSession.current_label, analysisMode: currentSession.analysis_mode)
        }
        return sessionStore.setup?.ready == true ? "Ready" : "Waiting"
    }

    private var liveReason: String {
        if let currentSession {
            return sessionStore.visibleReason(
                for: currentSession.current_label,
                reason: currentSession.short_reason,
                analysisMode: currentSession.analysis_mode
            )
        }
        return "Enable the camera, then start a session when you want the companion to begin watching for focus drift."
    }

    private var companionMessage: String {
        currentSession?.companion_message ?? "Defaults, privacy, and richer capture choices moved to Settings so this tab can stay calm."
    }

    private var liveTone: FocusBuddyTone {
        if let currentSession {
            return currentSession.current_label.tone
        }
        return sessionStore.setup?.ready == true ? .good : .caution
    }

    private var sessionStatusTone: FocusBuddyTone {
        if let currentSession {
            switch currentSession.status {
            case .running:
                return .good
            case .paused:
                return .caution
            case .stopped:
                return .neutral
            case .created:
                return .neutral
            }
        }
        return backendManager.state.tone
    }

    private var focusRatioValue: String {
        guard let currentSession else { return "—" }
        return DisplayFormat.percentage(currentSession.summary.focus_ratio)
    }

    private var reviewCountValue: String {
        guard let currentSession else { return "0" }
        return "\(currentSession.summary.total_reviews)"
    }

    private var keyframeCountValue: String {
        guard let currentSession else { return "0" }
        return "\(currentSession.keyframe_count)"
    }

    private var focusedCountValue: String {
        guard let currentSession else { return "0" }
        return "\(currentSession.summary.label_counts["focused"] ?? 0)"
    }

    private var distractedCountValue: String {
        guard let currentSession else { return "0" }
        return "\(currentSession.summary.label_counts["distracted"] ?? 0)"
    }

    private var awayCountValue: String {
        guard let currentSession else { return "0" }
        return "\(currentSession.summary.label_counts["away"] ?? 0)"
    }

    private var sessionDefaultsLine: String {
        [
            sessionStore.runtimeProfile.title,
            sessionStore.analysisMode.title,
            sessionStore.liveCoachingMode.title,
            sessionStore.includeScreenAnalysis ? "Screen on" : "Camera only",
        ].joined(separator: " · ")
    }

    private var cameraSourceBinding: Binding<String> {
        Binding(
            get: { sessionStore.selectedCameraSourceID },
            set: { nextID in
                Task { await sessionStore.selectCameraSource(nextID) }
            }
        )
    }
}
