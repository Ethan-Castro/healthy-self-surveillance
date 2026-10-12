import SwiftUI

enum FocusBuddyTone {
    case neutral
    case good
    case caution
    case critical

    var tint: Color {
        switch self {
        case .neutral:
            return Color.white.opacity(0.72)
        case .good:
            return Color(red: 0.68, green: 0.89, blue: 0.78)
        case .caution:
            return Color(red: 0.98, green: 0.84, blue: 0.54)
        case .critical:
            return Color(red: 0.98, green: 0.63, blue: 0.57)
        }
    }
}

struct AppBackground: View {
    var body: some View {
        ZStack {
            LinearGradient(
                colors: [
                    Color(red: 0.95, green: 0.90, blue: 0.82),
                    Color(red: 0.87, green: 0.92, blue: 0.97),
                ],
                startPoint: .topLeading,
                endPoint: .bottomTrailing
            )
            .ignoresSafeArea()

            Circle()
                .fill(Color.white.opacity(0.35))
                .frame(width: 360, height: 360)
                .blur(radius: 40)
                .offset(x: -320, y: -260)

            Circle()
                .fill(Color(red: 0.70, green: 0.83, blue: 0.95).opacity(0.32))
                .frame(width: 420, height: 420)
                .blur(radius: 60)
                .offset(x: 340, y: 180)
        }
    }
}

struct GlassSection<Content: View>: View {
    let title: String
    var subtitle: String? = nil
    @ViewBuilder let content: Content

    init(title: String, subtitle: String? = nil, @ViewBuilder content: () -> Content) {
        self.title = title
        self.subtitle = subtitle
        self.content = content()
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 18) {
            VStack(alignment: .leading, spacing: 6) {
                Text(title)
                    .font(.system(size: 24, weight: .bold, design: .rounded))
                if let subtitle {
                    Text(subtitle)
                        .font(.system(size: 14, weight: .medium))
                        .foregroundStyle(.secondary)
                }
            }

            content
        }
        .padding(22)
        .focusBuddyMaterial(cornerRadius: 28)
    }
}

struct GlassBanner: View {
    let title: String
    let message: String
    var tone: FocusBuddyTone = .neutral

    var body: some View {
        HStack(alignment: .top, spacing: 14) {
            Image(systemName: tone == .critical ? "exclamationmark.triangle.fill" : "info.circle.fill")
                .font(.system(size: 18, weight: .bold))
                .foregroundStyle(tone.tint)

            VStack(alignment: .leading, spacing: 4) {
                Text(title)
                    .font(.headline)
                Text(message)
                    .font(.subheadline)
                    .foregroundStyle(.secondary)
            }
        }
        .padding(16)
        .focusBuddyMaterial(cornerRadius: 22)
        .overlay(
            RoundedRectangle(cornerRadius: 22, style: .continuous)
                .stroke(tone.tint.opacity(0.45), lineWidth: 1)
        )
    }
}

struct StatusChip: View {
    let label: String
    var tone: FocusBuddyTone = .neutral

    var body: some View {
        Text(label)
            .font(.system(size: 12, weight: .semibold, design: .rounded))
            .foregroundStyle(Color.black.opacity(0.78))
            .padding(.horizontal, 10)
            .padding(.vertical, 6)
            .background(tone.tint, in: Capsule())
    }
}

struct MetricTile: View {
    let title: String
    let value: String
    var footnote: String? = nil

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text(title.uppercased())
                .font(.system(size: 11, weight: .semibold, design: .rounded))
                .tracking(0.8)
                .foregroundStyle(.secondary)

            Text(value)
                .font(.system(size: 24, weight: .bold, design: .rounded))

            if let footnote {
                Text(footnote)
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(16)
        .background(Color.white.opacity(0.42), in: RoundedRectangle(cornerRadius: 20, style: .continuous))
    }
}

struct FloatingTabBar: View {
    @Binding var selectedTab: NavigationTab

    var body: some View {
        HStack(spacing: 8) {
            ForEach(NavigationTab.allCases) { tab in
                Button {
                    selectedTab = tab
                } label: {
                    VStack(spacing: 6) {
                        Image(systemName: tab.symbolName)
                            .font(.system(size: 17, weight: .semibold))
                        Text(tab.title)
                            .font(.system(size: 11, weight: .semibold, design: .rounded))
                    }
                    .foregroundStyle(selectedTab == tab ? Color.black.opacity(0.82) : Color.primary.opacity(0.55))
                    .frame(maxWidth: .infinity)
                    .padding(.vertical, 10)
                    .background {
                        if selectedTab == tab {
                            Capsule()
                                .fill(Color.white.opacity(0.54))
                                .allowsHitTesting(false)
                        }
                    }
                }
                .buttonStyle(.plain)
                .contentShape(Rectangle())
            }
        }
        .padding(10)
        .focusBuddyMaterial(cornerRadius: 30)
        .overlay(
            RoundedRectangle(cornerRadius: 30, style: .continuous)
                .stroke(Color.white.opacity(0.55), lineWidth: 1)
                .allowsHitTesting(false)
        )
        // Upgrade point: replace this material container with Apple's Liquid Glass APIs
        // once the project is built with the macOS 26 SDK.
        .shadow(color: Color.black.opacity(0.08), radius: 20, x: 0, y: 10)
        .zIndex(10)
    }
}

struct EmptyStateCard: View {
    let title: String
    let message: String

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text(title)
                .font(.headline)
            Text(message)
                .font(.subheadline)
                .foregroundStyle(.secondary)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(18)
        .background(Color.white.opacity(0.32), in: RoundedRectangle(cornerRadius: 20, style: .continuous))
    }
}

struct SectionHeading: View {
    let title: String
    var caption: String? = nil

    var body: some View {
        HStack(alignment: .firstTextBaseline) {
            Text(title)
                .font(.headline)
            Spacer()
            if let caption {
                Text(caption)
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
        }
    }
}

extension View {
    func focusBuddyMaterial(cornerRadius: CGFloat) -> some View {
        modifier(FocusBuddyMaterialModifier(cornerRadius: cornerRadius))
    }
}

private struct FocusBuddyMaterialModifier: ViewModifier {
    let cornerRadius: CGFloat

    func body(content: Content) -> some View {
        content
            .background(
                .ultraThinMaterial,
                in: RoundedRectangle(cornerRadius: cornerRadius, style: .continuous)
            )
            .overlay(
                RoundedRectangle(cornerRadius: cornerRadius, style: .continuous)
                    .stroke(Color.white.opacity(0.46), lineWidth: 1)
                    .allowsHitTesting(false)
            )
            .shadow(color: Color.black.opacity(0.06), radius: 24, x: 0, y: 12)
    }
}

extension FocusLabel {
    var tone: FocusBuddyTone {
        switch self {
        case .focused:
            return .good
        case .drifting:
            return .caution
        case .distracted, .away:
            return .critical
        }
    }
}

extension BackendManager.State {
    var title: String {
        switch self {
        case .idle:
            return "Idle"
        case .launching:
            return "Launching backend"
        case .connected:
            return "Backend connected"
        case .failed:
            return "Backend unavailable"
        }
    }

    var tone: FocusBuddyTone {
        switch self {
        case .idle:
            return .neutral
        case .launching:
            return .caution
        case .connected:
            return .good
        case .failed:
            return .critical
        }
    }
}

enum DisplayFormat {
    static func timestamp(_ raw: String?) -> String {
        guard let raw else { return "Not yet" }
        guard let date = Self.makeISOFormatter().date(from: raw) else { return raw }
        return date.formatted(date: .omitted, time: .shortened)
    }

    static func shortDateTime(_ raw: String?) -> String {
        guard let raw else { return "Not yet" }
        guard let date = Self.makeISOFormatter().date(from: raw) else { return raw }
        return date.formatted(date: .abbreviated, time: .shortened)
    }

    static func percentage(_ value: Double) -> String {
        NumberFormatter.percent.string(from: NSNumber(value: value)) ?? "0%"
    }

    static func duration(milliseconds: Int?) -> String {
        guard let milliseconds else { return "—" }
        let totalSeconds = max(0, milliseconds / 1_000)
        let minutes = totalSeconds / 60
        let seconds = totalSeconds % 60
        if minutes > 0 {
            return "\(minutes)m \(seconds)s"
        }
        return "\(seconds)s"
    }

    private static func makeISOFormatter() -> ISO8601DateFormatter {
        ISO8601DateFormatter()
    }
}

private extension NumberFormatter {
    static let percent: NumberFormatter = {
        let formatter = NumberFormatter()
        formatter.numberStyle = .percent
        formatter.maximumFractionDigits = 0
        return formatter
    }()
}
