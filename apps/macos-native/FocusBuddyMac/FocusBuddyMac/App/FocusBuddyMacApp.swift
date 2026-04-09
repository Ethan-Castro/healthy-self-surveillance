import SwiftUI

@main
struct FocusBuddyMacApp: App {
    @StateObject private var appModel = AppModel()

    var body: some Scene {
        WindowGroup {
            ContentView()
                .environmentObject(appModel)
                .frame(minWidth: 1080, minHeight: 780)
        }
        .windowResizability(.contentMinSize)
    }
}
