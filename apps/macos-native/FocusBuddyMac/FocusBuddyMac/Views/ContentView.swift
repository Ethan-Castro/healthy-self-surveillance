import SwiftUI

struct ContentView: View {
    @EnvironmentObject private var appModel: AppModel

    var body: some View {
        ZStack {
            AppBackground()

            activeTabContent
            .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .top)
        }
        .safeAreaInset(edge: .bottom, spacing: 0) {
            FloatingTabBar(selectedTab: $appModel.selectedTab)
                .padding(.horizontal, 28)
                .padding(.top, 12)
                .padding(.bottom, 18)
        }
        .task {
            await appModel.start()
        }
        .overlay(alignment: .top) {
            if let message = appModel.globalError {
                GlassBanner(
                    title: "Backend issue",
                    message: message,
                    tone: .critical
                )
                .padding(.top, 20)
                .padding(.horizontal, 28)
            }
        }
    }

    @ViewBuilder
    private var activeTabContent: some View {
        switch appModel.selectedTab {
        case .live:
            LiveTabView(
                sessionStore: appModel.sessionStore,
                permissionsManager: appModel.permissionsManager,
                cameraManager: appModel.cameraManager,
                backendManager: appModel.backendManager,
                liquidGlassMessage: appModel.configuration.liquidGlassPrerequisiteMessage
            )
        case .review:
            ReviewTabView(reviewStore: appModel.reviewStore, apiClient: appModel.apiClient)
        case .insights:
            InsightsTabView(analyticsStore: appModel.analyticsStore, reviewStore: appModel.reviewStore)
        case .settings:
            SettingsTabView(
                preferencesStore: appModel.preferencesStore,
                sessionStore: appModel.sessionStore,
                permissionsManager: appModel.permissionsManager,
                backendManager: appModel.backendManager,
                configuration: appModel.configuration
            )
        }
    }
}
