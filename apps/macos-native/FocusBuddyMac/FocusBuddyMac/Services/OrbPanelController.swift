import AppKit
import SwiftUI

@MainActor
final class OrbStateModel: ObservableObject {
    @Published var state = OrbDisplayState()
}

@MainActor
final class OrbPanelController {
    private let stateModel = OrbStateModel()
    private var panel: NSPanel?

    func setEnabled(_ enabled: Bool) {
        if enabled {
            show()
        } else {
            hide()
        }
    }

    func update(state: OrbDisplayState) {
        stateModel.state = state
    }

    private func show() {
        if panel == nil {
            let panel = NSPanel(
                contentRect: NSRect(x: 0, y: 0, width: 220, height: 172),
                styleMask: [.borderless, .nonactivatingPanel],
                backing: .buffered,
                defer: false
            )
            panel.isFloatingPanel = true
            panel.level = .statusBar
            panel.collectionBehavior = [.canJoinAllSpaces, .fullScreenAuxiliary, .stationary]
            panel.backgroundColor = .clear
            panel.hasShadow = false
            panel.isOpaque = false
            panel.hidesOnDeactivate = false
            panel.ignoresMouseEvents = false
            panel.contentView = NSHostingView(rootView: OrbPanelView().environmentObject(stateModel))
            self.panel = panel
            position(panel: panel)
        }

        panel?.orderFrontRegardless()
    }

    private func hide() {
        panel?.orderOut(nil)
    }

    private func position(panel: NSPanel) {
        guard let screen = NSScreen.main else { return }
        let frame = screen.visibleFrame
        let x = frame.midX - (panel.frame.width / 2)
        let y = frame.maxY - panel.frame.height - 12
        panel.setFrameOrigin(NSPoint(x: x, y: y))
    }
}

private struct OrbPanelView: View {
    @EnvironmentObject private var stateModel: OrbStateModel

    var body: some View {
        VStack(spacing: 8) {
            ZStack {
                Circle()
                    .fill(orbGradient)
                    .overlay(alignment: .topLeading) {
                        Circle()
                            .fill(.white.opacity(0.32))
                            .frame(width: 26, height: 26)
                            .blur(radius: 6)
                            .offset(x: 18, y: 16)
                    }
                    .frame(width: 72, height: 72)

                HStack(spacing: 16) {
                    Circle().fill(Color.black.opacity(0.76)).frame(width: 8, height: 10)
                    Circle().fill(Color.black.opacity(0.76)).frame(width: 8, height: 10)
                }
                .offset(y: -4)

                Capsule()
                    .stroke(Color.black.opacity(0.76), lineWidth: 2)
                    .frame(width: 18, height: 8)
                    .offset(y: 18)
            }

            Text(stateModel.state.display_title)
                .font(.system(size: 13, weight: .semibold))
                .foregroundStyle(.primary)

            if stateModel.state.is_active {
                Text(stateModel.state.reason)
                    .font(.system(size: 11, weight: .medium))
                    .foregroundStyle(.secondary)
                    .multilineTextAlignment(.center)
                    .lineLimit(2)
                    .frame(maxWidth: 180)
            } else {
                Text("Native orb ready")
                    .font(.system(size: 11, weight: .medium))
                    .foregroundStyle(.secondary)
            }
        }
        .padding(.horizontal, 18)
        .padding(.vertical, 14)
        .background(
            RoundedRectangle(cornerRadius: 28, style: .continuous)
                .fill(.ultraThinMaterial)
                .overlay(
                    RoundedRectangle(cornerRadius: 28, style: .continuous)
                        .stroke(Color.white.opacity(0.5), lineWidth: 1)
                )
        )
        .padding(10)
    }

    private var orbGradient: LinearGradient {
        switch stateModel.state.label {
        case .focused:
            return LinearGradient(colors: [Color(red: 0.88, green: 0.96, blue: 1.0), Color(red: 0.47, green: 0.72, blue: 0.89)], startPoint: .topLeading, endPoint: .bottomTrailing)
        case .drifting:
            return LinearGradient(colors: [Color(red: 0.90, green: 0.92, blue: 1.0), Color(red: 0.55, green: 0.66, blue: 0.86)], startPoint: .topLeading, endPoint: .bottomTrailing)
        case .distracted:
            return LinearGradient(colors: [Color(red: 0.93, green: 0.93, blue: 0.93), Color(red: 0.48, green: 0.50, blue: 0.54)], startPoint: .topLeading, endPoint: .bottomTrailing)
        case .away:
            return LinearGradient(colors: [Color(red: 0.95, green: 0.96, blue: 0.98), Color(red: 0.66, green: 0.70, blue: 0.77)], startPoint: .topLeading, endPoint: .bottomTrailing)
        }
    }
}
