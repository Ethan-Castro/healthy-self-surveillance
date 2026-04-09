import SwiftUI

struct InsightsTabView: View {
    @ObservedObject var analyticsStore: AnalyticsStore
    @ObservedObject var reviewStore: ReviewStore

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 24) {
                header

                if let errorMessage = analyticsStore.errorMessage {
                    GlassBanner(title: "Insights issue", message: errorMessage, tone: .critical)
                }

                todaySection
                weekSection
                insightCardsSection
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
        GlassSection(title: "Insights", subtitle: "After-session learning, not a wall of dashboards.") {
            HStack(alignment: .top) {
                VStack(alignment: .leading, spacing: 8) {
                    Text("See how you did today, where your strongest conditions show up, and which patterns are worth testing next.")
                        .font(.subheadline)
                        .foregroundStyle(.secondary)
                    Text("Updated \(DisplayFormat.shortDateTime(analyticsStore.today?.generated_at ?? analyticsStore.week?.generated_at))")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
                Spacer()
                Button("Refresh") {
                    Task { await analyticsStore.refresh() }
                }
                .buttonStyle(.bordered)
            }
        }
    }

    private var todaySection: some View {
        GlassSection(title: "Today", subtitle: "Your current-day focus picture at a glance.") {
            if let today = analyticsStore.today?.today {
                VStack(alignment: .leading, spacing: 18) {
                    HStack(spacing: 16) {
                        MetricTile(title: "Focus ratio", value: DisplayFormat.percentage(today.avg_focus_ratio))
                        MetricTile(title: "Focused time", value: DisplayFormat.duration(milliseconds: today.total_focused_ms))
                        MetricTile(title: "Recovery", value: DisplayFormat.duration(milliseconds: today.avg_recovery_ms))
                        MetricTile(title: "Sessions", value: "\(today.session_count)")
                    }

                    SectionHeading(title: "Best hours", caption: today.best_hour_blocks.isEmpty ? "No hour trends yet" : nil)
                    comparisonGrid(today.best_hour_blocks.map {
                        ComparisonPoint(
                            dimension: "hour",
                            key: "\($0.hour):00",
                            sample_size: $0.sample_size,
                            session_count: $0.sample_size,
                            avg_focus_ratio: $0.focus_ratio,
                            avg_recovery_ms: nil,
                            avg_session_length_ms: 0,
                            confidence: $0.sample_size >= 4 ? .high : .medium
                        )
                    })
                }
            } else {
                EmptyStateCard(
                    title: "Today is still quiet",
                    message: "Complete a few sessions and this tab will start surfacing your best hours and strongest conditions."
                )
            }
        }
    }

    private var weekSection: some View {
        GlassSection(title: "Trends", subtitle: "Weekly consistency and condition comparisons.") {
            if let week = analyticsStore.week?.week {
                VStack(alignment: .leading, spacing: 18) {
                    HStack(spacing: 16) {
                        MetricTile(title: "Average focus", value: DisplayFormat.percentage(week.avg_focus_ratio))
                        MetricTile(title: "Average recovery", value: DisplayFormat.duration(milliseconds: week.avg_recovery_ms))
                        MetricTile(title: "Sessions", value: "\(week.session_count)")
                        MetricTile(
                            title: "Consistency",
                            value: week.consistency_delta.map { String(format: "%+.2f", $0) } ?? "—",
                            footnote: "Week over week"
                        )
                    }

                    SectionHeading(title: "Best conditions")
                    comparisonGrid(week.best_conditions)

                    SectionHeading(title: "Watch-outs")
                    comparisonGrid(week.weakest_conditions)
                }
            } else {
                EmptyStateCard(
                    title: "Weekly trends need more history",
                    message: "Once you save a handful of sessions, Focus Buddy will compare stronger and weaker conditions here."
                )
            }
        }
    }

    private var insightCardsSection: some View {
        GlassSection(title: "Patterns", subtitle: "Evidence-backed observations from the local analytics layer.") {
            let selectedInsights = reviewStore.analyticsDetail?.insights ?? []
            let combined = selectedInsights.isEmpty ? analyticsStore.insights : selectedInsights

            if combined.isEmpty {
                EmptyStateCard(
                    title: "No pattern cards yet",
                    message: "Once there is enough evidence, this area will point out recurring triggers, recovery patterns, and strong environments."
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
        GlassSection(title: "Experiments", subtitle: "Compare the conditions you might want to repeat or avoid.") {
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
                    title: "No experiments yet",
                    message: "Tag sessions by location, time, or environment and this section will start comparing what helps and what hurts."
                )
            }
        }
    }

    private var remarkableSection: some View {
        GlassSection(title: "Remarkable", subtitle: "Moments you explicitly kept for longer-term reflection.") {
            let moments = reviewStore.analyticsDetail?.remarkable_moments ?? []
            if moments.isEmpty {
                EmptyStateCard(
                    title: "Nothing marked remarkable yet",
                    message: "Use the Review tab to star a whole session or a specific moment that you want to keep."
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

    private func comparisonGrid(_ points: [ComparisonPoint]) -> some View {
        VStack(spacing: 10) {
            if points.isEmpty {
                EmptyStateCard(title: "No comparison data yet", message: "Save more sessions with context enabled to populate this comparison.")
            } else {
                ForEach(points) { point in
                    HStack(alignment: .top) {
                        VStack(alignment: .leading, spacing: 6) {
                            Text(point.key)
                                .font(.headline)
                            Text("\(point.dimension.capitalized) · \(point.sample_size) samples")
                                .font(.caption)
                                .foregroundStyle(.secondary)
                        }
                        Spacer()
                        VStack(alignment: .trailing, spacing: 6) {
                            Text(DisplayFormat.percentage(point.avg_focus_ratio))
                                .font(.headline)
                            Text(point.confidence.rawValue.capitalized)
                                .font(.caption)
                                .foregroundStyle(.secondary)
                        }
                    }
                    .padding(16)
                    .background(Color.white.opacity(0.35), in: RoundedRectangle(cornerRadius: 20, style: .continuous))
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
