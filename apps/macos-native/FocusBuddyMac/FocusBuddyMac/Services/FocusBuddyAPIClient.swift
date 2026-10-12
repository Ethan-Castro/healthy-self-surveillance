import Foundation

enum APIClientError: LocalizedError {
    case invalidURL
    case invalidResponse
    case serviceUnavailable(String)
    case requestFailed(String)

    var errorDescription: String? {
        switch self {
        case .invalidURL:
            return "The Focus Buddy API URL is invalid."
        case .invalidResponse:
            return "The Focus Buddy service returned an invalid response."
        case .serviceUnavailable(let message):
            return message
        case .requestFailed(let message):
            return message
        }
    }
}

private struct EmptyPayload: Codable {}
private struct SessionCreatePayload: Codable { let config: SessionConfig }
private struct PreferencesPayload: Codable { let preferences: AnalyticsPreferences }

final class FocusBuddyAPIClient: @unchecked Sendable {
    let baseURL: URL
    private let session: URLSession
    private let decoder = JSONDecoder()
    private let encoder = JSONEncoder()

    init(baseURL: URL, session: URLSession = .shared) {
        self.baseURL = baseURL
        self.session = session
    }

    func healthcheck() async throws -> HealthStatus {
        try await request(path: "/health", method: "GET", body: Optional<EmptyPayload>.none)
    }

    func fetchSetup() async throws -> SetupStatus {
        try await request(path: "/api/setup", method: "GET", body: Optional<EmptyPayload>.none)
    }

    func fetchPreferences() async throws -> AnalyticsPreferences {
        try await request(path: "/api/preferences", method: "GET", body: Optional<EmptyPayload>.none)
    }

    func updatePreferences(_ preferences: AnalyticsPreferences) async throws -> AnalyticsPreferences {
        try await request(path: "/api/preferences", method: "PUT", body: PreferencesPayload(preferences: preferences))
    }

    func listSessions() async throws -> [SessionSnapshot] {
        try await request(path: "/api/sessions", method: "GET", body: Optional<EmptyPayload>.none)
    }

    func createSession(config: SessionConfig) async throws -> SessionSnapshot {
        try await request(path: "/api/sessions", method: "POST", body: SessionCreatePayload(config: config))
    }

    func fetchSession(id: String) async throws -> SessionSnapshot {
        try await request(path: "/api/sessions/\(id)", method: "GET", body: Optional<EmptyPayload>.none)
    }

    func fetchSessionReview(id: String) async throws -> SessionReviewDetail {
        try await request(path: "/api/sessions/\(id)/review", method: "GET", body: Optional<EmptyPayload>.none)
    }

    func fetchSessionAnalytics(id: String) async throws -> SessionAnalyticsDetail {
        try await request(path: "/api/sessions/\(id)/analytics", method: "GET", body: Optional<EmptyPayload>.none)
    }

    func transitionSession(id: String, action: String) async throws -> SessionSnapshot {
        try await request(path: "/api/sessions/\(id)/\(action)", method: "POST", body: EmptyPayload())
    }

    func submitReview(id: String, review: ReviewInput) async throws -> SessionSnapshot {
        try await request(path: "/api/sessions/\(id)/review", method: "POST", body: review)
    }

    func submitContext(id: String, context: ContextCaptureRequest) async throws -> SessionSnapshot {
        try await request(path: "/api/sessions/\(id)/context", method: "POST", body: context)
    }

    func saveSession(id: String) async throws -> SessionSnapshot {
        try await request(path: "/api/sessions/\(id)/save", method: "POST", body: Optional<EmptyPayload>.none)
    }

    func rescanSession(id: String) async throws -> RescanResult {
        try await request(path: "/api/sessions/\(id)/rescan", method: "POST", body: Optional<EmptyPayload>.none)
    }

    func markSessionRemarkable(id: String, request remarkable: RemarkableRequest) async throws -> SessionSnapshot {
        try await request(path: "/api/sessions/\(id)/remarkable", method: "POST", body: remarkable)
    }

    func markMomentRemarkable(id: String, sequence: Int, request remarkable: RemarkableRequest) async throws -> SessionSnapshot {
        try await request(path: "/api/sessions/\(id)/moments/\(sequence)/remarkable", method: "POST", body: remarkable)
    }

    func clearMomentRemarkable(id: String, sequence: Int) async throws -> SessionSnapshot {
        try await request(path: "/api/sessions/\(id)/moments/\(sequence)/remarkable", method: "DELETE", body: Optional<EmptyPayload>.none)
    }

    func fetchTodayAnalytics() async throws -> DayAnalyticsView {
        try await request(path: "/api/analytics/today", method: "GET", body: Optional<EmptyPayload>.none)
    }

    func fetchWeekAnalytics() async throws -> WeekAnalyticsView {
        try await request(path: "/api/analytics/week", method: "GET", body: Optional<EmptyPayload>.none)
    }

    func fetchExperimentAnalytics() async throws -> ExperimentComparisonView {
        try await request(path: "/api/analytics/experiments", method: "GET", body: Optional<EmptyPayload>.none)
    }

    func fetchAnalyticsInsights() async throws -> [InsightCard] {
        try await request(path: "/api/analytics/insights", method: "GET", body: Optional<EmptyPayload>.none)
    }

    func keyframeURL(sessionID: String, keyframePath: String?) -> URL? {
        guard let keyframePath else { return nil }
        return keyframeURL(sessionID: sessionID, filename: keyframePath.split(separator: "/").last.map(String.init))
    }

    func keyframeURL(sessionID: String, filename: String?) -> URL? {
        guard let filename, !filename.isEmpty else { return nil }
        return baseURL.appending(path: "/api/sessions/\(sessionID)/keyframes/\(filename)")
    }

    private func request<T: Decodable, Body: Encodable>(
        path: String,
        method: String,
        body: Body?
    ) async throws -> T {
        guard let url = URL(string: path, relativeTo: baseURL) else {
            throw APIClientError.invalidURL
        }

        var request = URLRequest(url: url)
        request.httpMethod = method
        request.timeoutInterval = 45

        if let body {
            request.httpBody = try encoder.encode(body)
            request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        }

        let data: Data
        let response: URLResponse
        do {
            (data, response) = try await session.data(for: request)
        } catch {
            throw APIClientError.serviceUnavailable("Cannot reach the local Focus Buddy service at \(baseURL.absoluteString). \(error.localizedDescription)")
        }

        guard let httpResponse = response as? HTTPURLResponse else {
            throw APIClientError.invalidResponse
        }

        guard (200..<300).contains(httpResponse.statusCode) else {
            let detail = (try? JSONSerialization.jsonObject(with: data) as? [String: Any])?["detail"] as? String
            let fallback = String(data: data, encoding: .utf8) ?? "Request failed with \(httpResponse.statusCode)"
            throw APIClientError.requestFailed(detail ?? fallback)
        }

        return try decoder.decode(T.self, from: data)
    }
}
