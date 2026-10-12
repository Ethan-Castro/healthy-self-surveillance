import SwiftUI

struct PatternsTabView: View {
    @ObservedObject var analyticsStore: AnalyticsStore
    @ObservedObject var reviewStore: ReviewStore

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 24) {
                header

                sessionInsightsSection
                experimentsSection
                remarkableSection
            }
            .padding(.horizontal, 28)
            .padding(.top, 24)
            .padding(.bottom, 116)
        }
        .scrollIndicators(.hidden)
    }

    private var header: some View {
        GlassSection(title: "Patterns", subtitle: "Local insight cards and experiment comparisons across your saved sessions.") {
            Text("Patterns stay evidence-backed: confidence, sample size, and session range are visible so the app does not overstate weak trends.")
                .font(.subheadline)
                .foregroundStyle(.secondary)
        }
    }

    private var sessionInsightsSection: some View {
        GlassSection(title: "Insights", subtitle: "Structured summaries from the local analytics layer.") {
            let selectedInsights = reviewStore.analyticsDetail?.insights ?? []
            let combined = selectedInsights.isEmpty ? analyticsStore.insights : selectedInsights

            if combined.isEmpty {
                EmptyStateCard(
                    title: "No insight cards yet",
                    message: "Save more sessions so the analytics layer has enough evidence to surface recurring triggers, recovery patterns, and best conditions."
                )
            } else {
                VStack(spacing: 12) {
                    ForEach(combined) { insight in
                        VStack(alignment: .leading, spacing: 8) {
                            HStack {
                                Text(insight.title)
                                    .font(.headline)
                                Spacer()
                                StatusChip(label: insight.confidence.rawValue.capitalized, tone: tone(for: insight.confidence))
                            }
                            Text(insight.summary)
                                .font(.subheadline)
                            HStack(spacing: 12) {
                                Text(insight.category.rawValue.replacingOccurrences(of: "_", with: " ").capitalized)
                                Text("\(insight.sample_size) samples")
                                if let dateRange = insight.date_range {
                                    Text(dateRange)
                                }
                            }
                            .font(.caption)
                            .foregroundStyle(.secondary)
                        }
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .padding(16)
                        .background(Color.white.opacity(0.35), in: RoundedRectangle(cornerRadius: 22, style: .continuous))
                    }
                }
            }
        }
    }

    private var experimentsSection: some View {
        GlassSection(title: "Experiments", subtitle: "Compare conditions like location, time, and environment.") {
            if let experiments = analyticsStore.experiments, !experiments.dimensions.isEmpty {
                VStack(spacing: 16) {
                    ForEach(experiments.dimensions) { dimension in
                        VStack(alignment: .leading, spacing: 10) {
                            Text(dimension.dimension.capitalized)
                                .font(.headline)

                            ForEach(dimension.comparisons) { comparison in
                                HStack {
                                    VStack(alignment: .leading, spacing: 4) {
                                        Text(comparison.key)
                                            .font(.subheadline.weight(.semibold))
                                        Text("\(comparison.sample_size) samples")
                                            .font(.caption)
                                            .foregroundStyle(.secondary)
                                    }
                                    Spacer()
                                    VStack(alignment: .trailing, spacing: 4) {
                                        Text(DisplayFormat.percentage(comparison.avg_focus_ratio))
                                            .font(.headline)
                                        Text(comparison.confidence.rawValue.capitalized)
                                            .font(.caption)
                                            .foregroundStyle(.secondary)
                                    }
                                }
                                .padding(14)
                                .background(Color.white.opacity(0.35), in: RoundedRectangle(cornerRadius: 18, style: .continuous))
                            }
                        }
                    }
                }
            } else {
                EmptyStateCard(
                    title: "Experiment comparisons are still sparse",
                    message: "Once you tag sessions with location, environment, and other context, this area will compare the strongest and weakest conditions."
                )
            }
        }
    }

    private var remarkableSection: some View {
        GlassSection(title: "Remarkable", subtitle: "Sessions and moments you explicitly kept beyond the raw retention window.") {
            let moments = reviewStore.analyticsDetail?.remarkable_moments ?? []
            if moments.isEmpty {
                EmptyStateCard(
                    title: "Nothing marked remarkable yet",
                    message: "Use the Review tab to star a session or a specific timeline moment so it stays in long-term raw storage."
                )
            } else {
                VStack(spacing: 12) {
                    ForEach(moments) { moment in
                        HStack(alignment: .top) {
                            VStack(alignment: .leading, spacing: 6) {
                                Text(moment.session_level ? "Whole session" : "Moment \(moment.sequence ?? 0)")
                                    .font(.headline)
                                Text(DisplayFormat.shortDateTime(moment.created_at))
                                    .font(.caption)
                                    .foregroundStyle(.secondary)
                                if let note = moment.note, !note.isEmpty {
                                    Text(note)
                                        .font(.subheadline)
                                }
                            }
                            Spacer()
                            Image(systemName: "star.fill")
                                .foregroundStyle(Color.yellow)
                        }
                        .padding(16)
                        .background(Color.white.opacity(0.35), in: RoundedRectangle(cornerRadius: 20, style: .continuous))
                    }
                }
            }
        }
    }

    private func tone(for confidence: ConfidenceBucket) -> FocusBuddyTone {
        switch confidence {
        case .low:
            return .critical
        case .medium:
            return .caution
        case .high:
            return .good
        }
    }
}
