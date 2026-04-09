import SwiftUI

struct ReviewTabView: View {
    @ObservedObject var reviewStore: ReviewStore
    let apiClient: FocusBuddyAPIClient

    @State private var remarkableNote = ""

    var body: some View {
        HStack(alignment: .top, spacing: 24) {
            libraryColumn
            detailColumn
        }
        .padding(.horizontal, 28)
        .padding(.top, 24)
        .padding(.bottom, 116)
    }

    private var libraryColumn: some View {
        GlassSection(title: "Saved sessions", subtitle: "Your session library and native review entry point.") {
            ScrollView {
                VStack(spacing: 10) {
                    if reviewStore.sessions.isEmpty {
                        EmptyStateCard(
                            title: "No saved sessions yet",
                            message: "End and save a session from the Live tab to review it here."
                        )
                    } else {
                        ForEach(reviewStore.sessions) { session in
                            Button {
                                Task { await reviewStore.loadSession(id: session.session_id) }
                            } label: {
                                VStack(alignment: .leading, spacing: 8) {
                                    HStack {
                                        Text(session.session_name)
                                            .font(.headline)
                                        Spacer()
                                        if session.remarkable {
                                            Image(systemName: "star.fill")
                                                .foregroundStyle(Color.yellow)
                                        }
                                    }
                                    Text(DisplayFormat.shortDateTime(session.created_at))
                                        .font(.caption)
                                        .foregroundStyle(.secondary)
                                    HStack(spacing: 12) {
                                        Text("\(session.summary.total_reviews) reviews")
                                        Text("\(session.keyframe_count) keyframes")
                                    }
                                    .font(.caption)
                                    .foregroundStyle(.secondary)
                                }
                                .frame(maxWidth: .infinity, alignment: .leading)
                                .padding(16)
                                .background(
                                    (reviewStore.selectedSessionID == session.session_id ? Color.white.opacity(0.55) : Color.white.opacity(0.30)),
                                    in: RoundedRectangle(cornerRadius: 20, style: .continuous)
                                )
                            }
                            .buttonStyle(.plain)
                        }
                    }
                }
            }
            .scrollIndicators(.hidden)
        }
        .frame(width: 300)
    }

    private var detailColumn: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 24) {
                if let errorMessage = reviewStore.errorMessage {
                    GlassBanner(title: "Review issue", message: errorMessage, tone: .critical)
                }

                if let reviewDetail = reviewStore.reviewDetail {
                    sessionOverview(reviewDetail.session)

                    if let analyticsDetail = reviewStore.analyticsDetail {
                        metricsOverview(analyticsDetail.metrics)
                    }

                    timelineSection(title: "Live timeline", entries: reviewDetail.live_timeline)

                    if !reviewDetail.rescan_timeline.isEmpty {
                        timelineSection(title: "Rescan timeline", entries: reviewDetail.rescan_timeline)
                    }
                } else {
                    GlassSection(title: "After-session review", subtitle: "Select a saved session to inspect its timeline and keyframes.") {
                        EmptyStateCard(
                            title: "Pick a session",
                            message: "Saved sessions appear on the left. Once selected, you can inspect the timeline, mark remarkable moments, and rescan."
                        )
                    }
                }
            }
        }
        .scrollIndicators(.hidden)
        .frame(maxWidth: .infinity)
    }

    private func sessionOverview(_ session: SessionSnapshot) -> some View {
        GlassSection(title: session.session_name, subtitle: "Native review surface for keyframes, metrics, and remarkable moments.") {
            VStack(alignment: .leading, spacing: 18) {
                HStack(spacing: 16) {
                    MetricTile(title: "Focus ratio", value: DisplayFormat.percentage(session.summary.focus_ratio))
                    MetricTile(title: "Reviews", value: "\(session.summary.total_reviews)")
                    MetricTile(title: "Keyframes", value: "\(session.keyframe_count)")
                }

                TextField("Why was this session remarkable?", text: $remarkableNote)
                    .textFieldStyle(.roundedBorder)

                HStack(spacing: 12) {
                    Button("Mark session remarkable") {
                        Task { await reviewStore.markSelectedSessionRemarkable(note: remarkableNote.isEmpty ? nil : remarkableNote) }
                    }
                    .buttonStyle(.borderedProminent)

                    Button("Refresh session") {
                        guard let selectedSessionID = reviewStore.selectedSessionID else { return }
                        Task { await reviewStore.loadSession(id: selectedSessionID) }
                    }
                    .buttonStyle(.bordered)
                }
            }
        }
    }

    private func metricsOverview(_ metrics: SessionMetrics) -> some View {
        GlassSection(title: "Session metrics", subtitle: "Structured analytics derived from the saved review stream.") {
            VStack(alignment: .leading, spacing: 16) {
                HStack(spacing: 16) {
                    MetricTile(title: "Focused", value: DisplayFormat.duration(milliseconds: metrics.focused_ms))
                    MetricTile(title: "Unfocused", value: DisplayFormat.duration(milliseconds: metrics.unfocused_ms))
                    MetricTile(title: "Best streak", value: DisplayFormat.duration(milliseconds: metrics.longest_focus_streak_ms))
                    MetricTile(title: "Recovery", value: DisplayFormat.duration(milliseconds: metrics.avg_recovery_ms))
                }
                HStack(spacing: 16) {
                    MetricTile(title: "Drifts", value: "\(metrics.drift_count)")
                    MetricTile(title: "Distractions", value: "\(metrics.distraction_count)")
                    MetricTile(title: "Away", value: "\(metrics.away_count)")
                    MetricTile(title: "Nudge rate", value: DisplayFormat.percentage(metrics.nudge_effectiveness_rate))
                }
            }
        }
    }

    private func timelineSection(title: String, entries: [ReviewEntry]) -> some View {
        GlassSection(title: title, subtitle: "\(entries.count) moments") {
            VStack(spacing: 14) {
                ForEach(entries) { entry in
                    VStack(alignment: .leading, spacing: 12) {
                        HStack(alignment: .top, spacing: 14) {
                            keyframe(entry: entry)

                            VStack(alignment: .leading, spacing: 6) {
                                HStack {
                                    Text(entry.label.title)
                                        .font(.headline)
                                    Spacer()
                                    Text(DisplayFormat.timestamp(entry.timestamp))
                                        .font(.caption)
                                        .foregroundStyle(.secondary)
                                }
                                Text(entry.note)
                                    .font(.subheadline)
                                Text(entry.buddy_note)
                                    .font(.caption)
                                    .foregroundStyle(.secondary)
                            }
                        }

                        HStack(spacing: 12) {
                            if entry.remarkable {
                                Button("Clear remarkable") {
                                    Task { await reviewStore.clearMoment(sequence: entry.sequence) }
                                }
                                .buttonStyle(.bordered)
                            } else {
                                Button("Mark remarkable") {
                                    Task { await reviewStore.markMoment(sequence: entry.sequence, note: remarkableNote.isEmpty ? nil : remarkableNote) }
                                }
                                .buttonStyle(.bordered)
                            }

                            if let note = entry.remarkable_note, !note.isEmpty {
                                Text(note)
                                    .font(.caption)
                                    .foregroundStyle(.secondary)
                            }
                        }
                    }
                    .padding(16)
                    .background(Color.white.opacity(0.35), in: RoundedRectangle(cornerRadius: 22, style: .continuous))
                }
            }
        }
    }

    @ViewBuilder
    private func keyframe(entry: ReviewEntry) -> some View {
        if let keyframePath = entry.keyframe_path, let selectedSessionID = reviewStore.selectedSessionID {
            AsyncImage(url: apiClient.keyframeURL(sessionID: selectedSessionID, filename: URL(fileURLWithPath: keyframePath).lastPathComponent)) { phase in
                switch phase {
                case .success(let image):
                    image
                        .resizable()
                        .aspectRatio(contentMode: .fill)
                case .failure(_):
                    Color.white.opacity(0.22)
                        .overlay(Image(systemName: "photo").foregroundStyle(.secondary))
                case .empty:
                    ProgressView()
                @unknown default:
                    EmptyView()
                }
            }
            .frame(width: 128, height: 96)
            .clipShape(RoundedRectangle(cornerRadius: 18, style: .continuous))
        } else {
            RoundedRectangle(cornerRadius: 18, style: .continuous)
                .fill(Color.white.opacity(0.22))
                .frame(width: 128, height: 96)
                .overlay(Image(systemName: "photo").foregroundStyle(.secondary))
        }
    }
}
