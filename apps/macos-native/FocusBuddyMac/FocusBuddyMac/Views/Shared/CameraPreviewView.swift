import AppKit
import SwiftUI

struct CameraPreviewView: View {
    let image: NSImage?
    let isLive: Bool

    var body: some View {
        ZStack {
            RoundedRectangle(cornerRadius: 28, style: .continuous)
                .fill(Color.white.opacity(0.26))

            if let image {
                Image(nsImage: image)
                    .resizable()
                    .aspectRatio(contentMode: .fill)
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
                    .clipShape(RoundedRectangle(cornerRadius: 28, style: .continuous))
            } else {
                VStack(spacing: 12) {
                    Image(systemName: "video.slash.fill")
                        .font(.system(size: 34, weight: .semibold))
                        .foregroundStyle(.secondary)
                    Text(isLive ? "Waiting for camera frames." : "Camera preview will appear here once the camera is enabled.")
                        .font(.subheadline)
                        .foregroundStyle(.secondary)
                        .multilineTextAlignment(.center)
                        .frame(maxWidth: 280)
                }
            }
        }
        .aspectRatio(16.0 / 10.0, contentMode: .fit)
    }
}
