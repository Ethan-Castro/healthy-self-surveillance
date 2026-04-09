import SwiftUI

struct SettingsTabView: View {
    @ObservedObject var preferencesStore: PreferencesStore
    @ObservedObject var sessionStore: SessionStore
    @ObservedObject var permissionsManager: PermissionsManager
    @ObservedObject var backendManager: BackendManager
    let configuration: AppConfiguration

    @State private var showCaptureDefaults = false
    @State private var showManualDefaults = false
    @State private var showBackendLogs = false

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 24) {
                header

                if let errorMessage = preferencesStore.errorMessage {
                    GlassBanner(title: "Settings issue", message: errorMessage, tone: .critical)
                }

                sessionDefaultsSection
                privacySection
                permissionSection
                backendSection
            }
            .padding(.horizontal, 28)
            .padding(.top, 24)
            .padding(.bottom, 116)
        }
        .scrollIndicators(.hidden)
    }

    private var header: some View {
        GlassSection(title: "Settings", subtitle: "Where the product stays honest about defaults, privacy, and backend state.") {
            HStack(alignment: .top, spacing: 24) {
                VStack(alignment: .leading, spacing: 8) {
                    Text("Live is now the calm companion surface. Use this tab for session defaults, privacy choices, and backend visibility.")
                        .font(.subheadline)
                        .foregroundStyle(.secondary)
                    Text(configuration.liquidGlassPrerequisiteMessage)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }

                Spacer()

                Button("Save privacy settings") {
                    Task { await preferencesStore.save() }
                }
                .buttonStyle(.borderedProminent)
                .disabled(!preferencesStore.isDirty)
            }
        }
    }

    private var sessionDefaultsSection: some View {
        GlassSection(title: "Session defaults", subtitle: "These apply to the next live session. Privacy defaults save separately below.") {
            VStack(alignment: .leading, spacing: 18) {
                TextField("Default session name", text: $sessionStore.sessionName)
                    .textFieldStyle(.roundedBorder)

                HStack(alignment: .top, spacing: 16) {
                    VStack(alignment: .leading, spacing: 8) {
                        Text("Runtime profile")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                        Picker("Runtime profile", selection: $sessionStore.runtimeProfile) {
                            ForEach(runtimeOptions, id: \.self) { profile in
                                Text(profile.title).tag(profile)
                            }
                        }
                        .pickerStyle(.menu)
                    }
                    .frame(maxWidth: 220, alignment: .leading)

                    VStack(alignment: .leading, spacing: 8) {
                        Text("Review style")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                        Picker("Review style", selection: $sessionStore.analysisMode) {
                            ForEach(AnalysisMode.allCases, id: \.self) { mode in
                                Text(mode.title).tag(mode)
                            }
                        }
                        .pickerStyle(.segmented)
                    }
                }

                VStack(alignment: .leading, spacing: 8) {
                    Text("Live coaching")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                    Picker("Live coaching", selection: $preferencesStore.draft.live_coaching_mode) {
                        ForEach(LiveCoachingMode.allCases, id: \.self) { mode in
                            Text(mode.title).tag(mode)
                        }
                    }
                    .pickerStyle(.menu)
                    .frame(maxWidth: 240)
                }

                HStack(spacing: 16) {
                    Toggle("Use screen analysis by default", isOn: $sessionStore.includeScreenAnalysis)
                    Toggle("Show floating orb", isOn: $sessionStore.showOrb)
                    Toggle("Desktop nudges", isOn: $sessionStore.desktopNudgesEnabled)
                }

                VStack(alignment: .leading, spacing: 8) {
                    Text("Available on this Mac")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                    HStack(spacing: 10) {
                        ForEach(runtimeOptions, id: \.self) { profile in
                            StatusChip(
                                label: profile.title,
                                tone: profile == sessionStore.runtimeProfile ? .good : .neutral
                            )
                        }
                    }
                }
            }
        }
    }

    private var privacySection: some View {
        GlassSection(title: "Privacy and retention", subtitle: "Opt-in capture only, with raw evidence pruned locally after a short window.") {
            VStack(alignment: .leading, spacing: 16) {
                Stepper(
                    "Raw evidence retention: \(preferencesStore.draft.raw_retention_days) days",
                    value: $preferencesStore.draft.raw_retention_days,
                    in: 1...30
                )
                Toggle("Keep remarkable raw evidence", isOn: $preferencesStore.draft.keep_remarkable_raw)

                DisclosureGroup("Capture defaults", isExpanded: $showCaptureDefaults) {
                    VStack(alignment: .leading, spacing: 12) {
                        Toggle("Screen", isOn: captureToggleBinding(\.screen))
                        Toggle("App and window context", isOn: captureToggleBinding(\.app_context))
                        Toggle("Keyboard and mouse counts", isOn: captureToggleBinding(\.input_activity))
                        Toggle("Sound features", isOn: captureToggleBinding(\.sound_features))
                        Toggle("Location label", isOn: captureToggleBinding(\.location))
                        Toggle("Calendar context", isOn: captureToggleBinding(\.calendar_context))
                        Toggle("Manual tags", isOn: captureToggleBinding(\.manual_tags))
                    }
                    .padding(.top, 12)
                }

                DisclosureGroup("Default manual tags", isExpanded: $showManualDefaults) {
                    VStack(alignment: .leading, spacing: 12) {
                        HStack(spacing: 12) {
                            TextField("Task", text: defaultManualTextBinding(\.task))
                            TextField("Environment", text: defaultManualTextBinding(\.environment))
                            TextField("Location", text: defaultManualTextBinding(\.location_label))
                        }
                        HStack(spacing: 12) {
                            TextField("Mood", text: defaultManualTextBinding(\.mood))
                            TextField("Energy", text: defaultManualTextBinding(\.energy))
                            TextField("Caffeine", text: defaultManualTextBinding(\.caffeine))
                        }
                    }
                    .padding(.top, 12)
                }
            }
        }
    }

    private var permissionSection: some View {
        GlassSection(title: "Permissions", subtitle: "Native permission status for camera, microphone, notifications, and screen capture.") {
            VStack(alignment: .leading, spacing: 16) {
                HStack(spacing: 16) {
                    MetricTile(title: "Camera", value: permissionsManager.cameraAuthorized ? "Allowed" : "Not allowed")
                    MetricTile(title: "Microphone", value: permissionsManager.microphoneAuthorized ? "Allowed" : "Not allowed")
                    MetricTile(title: "Notifications", value: permissionsManager.notificationsAuthorized ? "Allowed" : "Not allowed")
                    MetricTile(title: "Screen", value: permissionsManager.screenCaptureAuthorized ? "Allowed" : "Not allowed")
                }

                HStack(spacing: 12) {
                    Button("Request camera") {
                        Task { _ = await permissionsManager.requestCamera() }
                    }
                    .buttonStyle(.bordered)

                    Button("Request microphone") {
                        Task { _ = await permissionsManager.requestMicrophone() }
                    }
                    .buttonStyle(.bordered)

                    Button("Request notifications") {
                        Task { _ = await permissionsManager.requestNotifications() }
                    }
                    .buttonStyle(.bordered)

                    Button("Request screen capture") {
                        _ = permissionsManager.requestScreenCapture()
                    }
                    .buttonStyle(.bordered)
                }
            }
        }
    }

    private var backendSection: some View {
        GlassSection(title: "Backend", subtitle: "The repo-local FastAPI service stays the source of truth for sessions, analytics, and review state.") {
            VStack(alignment: .leading, spacing: 14) {
                HStack {
                    StatusChip(label: backendManager.state.title, tone: backendManager.state.tone)
                    Spacer()
                    Text(configuration.apiBaseURL.absoluteString)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }

                DisclosureGroup("Backend logs", isExpanded: $showBackendLogs) {
                    ScrollView {
                        LazyVStack(alignment: .leading, spacing: 8) {
                            ForEach(Array(backendManager.logLines.enumerated()), id: \.offset) { _, line in
                                Text(line)
                                    .font(.system(size: 12, weight: .medium, design: .monospaced))
                                    .frame(maxWidth: .infinity, alignment: .leading)
                                    .padding(.vertical, 2)
                            }
                        }
                    }
                    .frame(minHeight: 220)
                    .padding(16)
                    .background(Color.black.opacity(0.08), in: RoundedRectangle(cornerRadius: 18, style: .continuous))
                    .padding(.top, 12)
                }
            }
        }
    }

    private var runtimeOptions: [RuntimeProfile] {
        let available = sessionStore.setup?.available_runtime_profiles ?? RuntimeProfile.allCases
        var ordered: [RuntimeProfile] = []
        for profile in [sessionStore.runtimeProfile] + available where !ordered.contains(profile) {
            ordered.append(profile)
        }
        return ordered
    }

    private func captureToggleBinding(_ keyPath: WritableKeyPath<DataSourceToggles, Bool>) -> Binding<Bool> {
        Binding(
            get: { preferencesStore.draft.capture_toggles[keyPath: keyPath] },
            set: { preferencesStore.draft.capture_toggles[keyPath: keyPath] = $0 }
        )
    }

    private func defaultManualTextBinding(_ keyPath: WritableKeyPath<ManualTags, String?>) -> Binding<String> {
        Binding(
            get: { preferencesStore.draft.default_manual_tags[keyPath: keyPath] ?? "" },
            set: { preferencesStore.draft.default_manual_tags[keyPath: keyPath] = $0.isEmpty ? nil : $0 }
        )
    }
}
