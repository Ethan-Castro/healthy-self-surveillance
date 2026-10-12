import Foundation

enum FocusLabel: String, Codable, CaseIterable {
    case focused
    case drifting
    case distracted
    case away

    var title: String {
        rawValue.capitalized
    }
}

enum SessionStatus: String, Codable {
    case created
    case running
    case paused
    case stopped
}

enum GemmaReviewStatus: String, Codable {
    case idle
    case reviewing
    case ready
    case error
}

enum ReviewMode: String, Codable {
    case live
    case rescan
}

enum RuntimeProfile: String, Codable, CaseIterable {
    case standard
    case higher_accuracy
    case edge

    var title: String {
        switch self {
        case .standard:
            return "Standard"
        case .higher_accuracy:
            return "Accurate"
        case .edge:
            return "Edge"
        }
    }
}

enum AnalysisMode: String, Codable, CaseIterable {
    case classification
    case annotation

    var title: String {
        switch self {
        case .classification:
            return "Focused / unfocused"
        case .annotation:
            return "Annotation"
        }
    }
}

enum LiveCoachingMode: String, Codable, CaseIterable {
    case off
    case notifications
    case ambient
    case full

    var title: String {
        switch self {
        case .off:
            return "Off"
        case .notifications:
            return "Notifications"
        case .ambient:
            return "Ambient"
        case .full:
            return "Full companion"
        }
    }
}

enum ContextCaptureReason: String, Codable {
    case interval
    case transition
    case nudge
    case manual
    case start
    case stop
}

enum SessionEventType: String, Codable {
    case session_started
    case session_paused
    case session_resumed
    case session_stopped
    case review_submitted
    case review_applied
    case label_transition
    case nudge_sent
    case recovery_detected
    case remarkable_marked
    case remarkable_cleared
    case context_captured
}

enum ConfidenceBucket: String, Codable {
    case low
    case medium
    case high
}

enum InsightCategory: String, Codable {
    case pattern
    case trigger
    case recovery
    case environment
    case experiment_result
    case consistency
}

struct DataSourceToggles: Codable, Equatable {
    var camera: Bool = true
    var screen: Bool = false
    var app_context: Bool = false
    var input_activity: Bool = false
    var sound_features: Bool = false
    var location: Bool = false
    var calendar_context: Bool = false
    var manual_tags: Bool = false

    static let `default` = DataSourceToggles()
}

struct ManualTags: Codable, Equatable {
    var task: String? = nil
    var mood: String? = nil
    var energy: String? = nil
    var caffeine: String? = nil
    var environment: String? = nil
    var location_label: String? = nil
    var note: String? = nil
    var phone_present: Bool? = nil

    static let empty = ManualTags()
}

struct AnalyticsPreferences: Codable, Equatable {
    var raw_retention_days: Int
    var keep_remarkable_raw: Bool
    var analytics_version: String
    var live_coaching_mode: LiveCoachingMode
    var capture_toggles: DataSourceToggles
    var default_manual_tags: ManualTags

    static let fallback = AnalyticsPreferences(
        raw_retention_days: 7,
        keep_remarkable_raw: true,
        analytics_version: "v1",
        live_coaching_mode: .notifications,
        capture_toggles: .default,
        default_manual_tags: .empty
    )
}

struct SetupStatus: Codable {
    var ready: Bool
    var model_name: String
    var runtime_profile: RuntimeProfile
    var available_runtime_profiles: [RuntimeProfile]
    var mode: String
    var message: String
    var checked_at: String
}

struct SessionConfig: Codable, Equatable {
    var session_name: String
    var include_screen_analysis: Bool
    var runtime_profile: RuntimeProfile
    var analysis_mode: AnalysisMode
    var live_coaching_mode: LiveCoachingMode
    var capture_toggles: DataSourceToggles
    var manual_tags: ManualTags
    var focused_review_cadence_ms: Int
    var active_review_cadence_ms: Int
    var timelapse_capture_interval_reviews: Int
    var temporary_review_window_sec: Int

    static let `default` = SessionConfig(
        session_name: "Focus Buddy Session",
        include_screen_analysis: false,
        runtime_profile: .standard,
        analysis_mode: .annotation,
        live_coaching_mode: .notifications,
        capture_toggles: .default,
        manual_tags: .empty,
        focused_review_cadence_ms: 1_200,
        active_review_cadence_ms: 650,
        timelapse_capture_interval_reviews: 1,
        temporary_review_window_sec: 600
    )
}

struct ReviewInput: Codable {
    var frame_sequence: Int
    var camera_image_b64: String?
    var screen_image_b64: String?
    var include_screen_analysis: Bool
    var device_id: String?
    var capture_source: String?
    var force_review: Bool?
}

struct ContextCaptureRequest: Codable {
    var timestamp: String? = nil
    var reason: ContextCaptureReason
    var device_id: String? = nil
    var capture_source: String? = nil
    var context_source: String? = nil
    var screen_enabled: Bool? = nil
    var app_name: String? = nil
    var window_title: String? = nil
    var app_category: String? = nil
    var system_idle_seconds: Int? = nil
    var system_idle_state: String? = nil
    var keyboard_events: Int? = nil
    var mouse_events: Int? = nil
    var scroll_events: Int? = nil
    var sound_rms: Double? = nil
    var sound_peak: Double? = nil
    var sound_bucket: String? = nil
    var location_label: String? = nil
    var calendar_title: String? = nil
    var calendar_category: String? = nil
    var manual_tags: ManualTags? = nil
    var phone_present: Bool? = nil
}

struct RemarkableRequest: Codable {
    var remarkable: Bool?
    var note: String?
}

struct SessionSummary: Codable {
    var total_reviews: Int
    var label_counts: [String: Int]
    var focus_ratio: Double
    var distraction_reviews: Int
    var most_common_reason: String?
}

struct ReviewEntry: Codable, Identifiable {
    var timestamp: String
    var sequence: Int
    var mode: ReviewMode
    var label: FocusLabel
    var confidence: Double
    var reasons: [String]
    var note: String
    var buddy_note: String
    var keyframe_path: String?
    var screen_used: Bool
    var capture_source: String?
    var remarkable: Bool
    var remarkable_note: String?

    var id: String {
        "\(mode.rawValue)-\(sequence)-\(timestamp)"
    }
}

struct SessionArtifacts: Codable {
    var session_dir: String
    var session_file: String
    var reviews_file: String
    var keyframes_dir: String
    var rescan_file: String
    var summary_file: String
    var events_file: String
    var contexts_file: String
    var metrics_file: String
    var insights_file: String
}

struct SessionSnapshot: Codable, Identifiable {
    var session_id: String
    var session_name: String
    var created_at: String
    var updated_at: String
    var status: SessionStatus
    var runtime_profile: RuntimeProfile
    var analysis_mode: AnalysisMode
    var live_coaching_mode: LiveCoachingMode
    var capture_toggles: DataSourceToggles
    var manual_tags: ManualTags
    var current_label: FocusLabel
    var short_reason: String
    var companion_message: String
    var review_status: GemmaReviewStatus
    var last_review_at: String?
    var include_screen_analysis: Bool
    var is_saved: Bool
    var temporary_expires_at: String?
    var summary: SessionSummary
    var recent_reviews: [ReviewEntry]
    var can_rescan: Bool
    var keyframe_count: Int
    var rescan_review_count: Int
    var remarkable: Bool
    var metrics_ready: Bool
    var analytics_version: String

    var id: String { session_id }
}

struct SessionReviewDetail: Codable {
    var session: SessionSnapshot
    var live_timeline: [ReviewEntry]
    var rescan_timeline: [ReviewEntry]
}

struct SessionEvent: Codable, Identifiable {
    var timestamp: String
    var type: SessionEventType
    var sequence: Int?
    var label: FocusLabel?
    var detail: String?
    var metadata: [String: PrimitiveMetricValue]

    var id: String {
        [timestamp, type.rawValue, sequence.map(String.init) ?? "none"].joined(separator: "-")
    }
}

enum PrimitiveMetricValue: Codable, Hashable {
    case string(String)
    case int(Int)
    case double(Double)
    case bool(Bool)
    case null

    init(from decoder: Decoder) throws {
        let container = try decoder.singleValueContainer()
        if container.decodeNil() {
            self = .null
        } else if let value = try? container.decode(Bool.self) {
            self = .bool(value)
        } else if let value = try? container.decode(Int.self) {
            self = .int(value)
        } else if let value = try? container.decode(Double.self) {
            self = .double(value)
        } else {
            self = .string(try container.decode(String.self))
        }
    }

    func encode(to encoder: Encoder) throws {
        var container = encoder.singleValueContainer()
        switch self {
        case .string(let value):
            try container.encode(value)
        case .int(let value):
            try container.encode(value)
        case .double(let value):
            try container.encode(value)
        case .bool(let value):
            try container.encode(value)
        case .null:
            try container.encodeNil()
        }
    }
}

struct ContextSnapshot: Codable, Identifiable {
    var timestamp: String
    var reason: ContextCaptureReason
    var device_id: String
    var capture_source: String
    var context_source: String
    var screen_enabled: Bool
    var app_name: String?
    var window_title: String?
    var app_category: String?
    var system_idle_seconds: Int?
    var system_idle_state: String?
    var keyboard_events: Int
    var mouse_events: Int
    var scroll_events: Int
    var sound_rms: Double?
    var sound_peak: Double?
    var sound_bucket: String?
    var location_label: String?
    var calendar_title: String?
    var calendar_category: String?
    var manual_tags: ManualTags
    var phone_present: Bool?

    var id: String { "\(timestamp)-\(reason.rawValue)" }
}

struct SessionMetrics: Codable {
    var session_length_ms: Int
    var focused_ms: Int
    var unfocused_ms: Int
    var drifting_ms: Int
    var distracted_ms: Int
    var away_ms: Int
    var focus_ratio: Double
    var longest_focus_streak_ms: Int
    var time_to_first_drift_ms: Int?
    var time_to_first_distraction_ms: Int?
    var drift_count: Int
    var distraction_count: Int
    var away_count: Int
    var recovery_count: Int
    var avg_recovery_ms: Int?
    var nudge_count: Int
    var nudge_effective_count: Int
    var nudge_effectiveness_rate: Double
    var focus_stability_score: Double
    var interruption_density: Double
    var label_transition_count: Int
    var context_capture_count: Int
    var last_computed_at: String
}

struct InsightCard: Codable, Identifiable {
    var id: String
    var category: InsightCategory
    var title: String
    var summary: String
    var confidence: ConfidenceBucket
    var sample_size: Int
    var supporting_metrics: [String: PrimitiveMetricValue]
    var date_range: String?
    var generated_by: String
}

struct RemarkableMoment: Codable, Identifiable {
    var created_at: String
    var sequence: Int?
    var session_level: Bool
    var note: String?
    var keyframe_path: String?

    var id: String {
        "\(created_at)-\(sequence.map(String.init) ?? "session")"
    }
}

struct ComparisonPoint: Codable, Identifiable {
    var dimension: String
    var key: String
    var sample_size: Int
    var session_count: Int
    var avg_focus_ratio: Double
    var avg_recovery_ms: Int?
    var avg_session_length_ms: Int
    var confidence: ConfidenceBucket

    var id: String {
        "\(dimension)-\(key)"
    }
}

struct ExperimentDimensionView: Codable, Identifiable {
    var dimension: String
    var comparisons: [ComparisonPoint]

    var id: String { dimension }
}

struct HourBlock: Codable, Identifiable {
    var hour: Int
    var sample_size: Int
    var focus_ratio: Double

    var id: Int { hour }
}

struct DayRollup: Codable {
    var date: String
    var session_count: Int
    var total_focused_ms: Int
    var total_unfocused_ms: Int
    var avg_focus_ratio: Double
    var avg_recovery_ms: Int?
    var best_hour_blocks: [HourBlock]
    var worst_hour_blocks: [HourBlock]
    var top_contexts: [ComparisonPoint]
    var insights: [InsightCard]
}

struct WeekRollup: Codable {
    var week_id: String
    var week_start: String
    var week_end: String
    var session_count: Int
    var avg_focus_ratio: Double
    var avg_recovery_ms: Int?
    var consistency_delta: Double?
    var best_conditions: [ComparisonPoint]
    var weakest_conditions: [ComparisonPoint]
    var insights: [InsightCard]
}

struct SessionAnalyticsDetail: Codable {
    var session: SessionSnapshot
    var metrics: SessionMetrics
    var insights: [InsightCard]
    var contexts: [ContextSnapshot]
    var events: [SessionEvent]
    var remarkable_moments: [RemarkableMoment]
    var privacy_ledger: DataSourceToggles
}

struct DayAnalyticsView: Codable {
    var generated_at: String
    var today: DayRollup
}

struct WeekAnalyticsView: Codable {
    var generated_at: String
    var week: WeekRollup
}

struct ExperimentComparisonView: Codable {
    var generated_at: String
    var dimensions: [ExperimentDimensionView]
    var insights: [InsightCard]
}

struct RescanResult: Codable {
    var session_id: String
    var revised_summary: SessionSummary
    var revised_timeline: [ReviewEntry]
    var artifact_paths: SessionArtifacts
    var persisted: Bool
}

struct HealthStatus: Codable {
    var status: String
    var setup_ready: Bool
    var model_name: String
    var runtime_profile: RuntimeProfile
    var available_runtime_profiles: [RuntimeProfile]
    var message: String
}

enum NavigationTab: String, CaseIterable, Identifiable {
    case live
    case review
    case insights
    case settings

    var id: String { rawValue }

    var title: String {
        switch self {
        case .live:
            return "Live"
        case .review:
            return "Review"
        case .insights:
            return "Insights"
        case .settings:
            return "Settings"
        }
    }

    var symbolName: String {
        switch self {
        case .live:
            return "house.fill"
        case .review:
            return "film.stack"
        case .insights:
            return "sparkles"
        case .settings:
            return "gearshape.fill"
        }
    }
}

struct OrbDisplayState: Equatable {
    var label: FocusLabel = .away
    var analysis_mode: AnalysisMode = .annotation
    var reason: String = "Waiting for a live session."
    var message: String = "The native orb will follow the active session."
    var is_active: Bool = false

    var display_title: String {
        if analysis_mode == .classification {
            return label == .focused ? "Focused" : "Unfocused"
        }
        return label.title
    }
}
