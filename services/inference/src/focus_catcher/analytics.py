from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timedelta
from statistics import mean

from .models import (
    ComparisonPoint,
    ConfidenceBucket,
    ContextSnapshot,
    DayRollup,
    ExperimentComparisonView,
    ExperimentDimensionView,
    FocusLabel,
    HourBlock,
    InsightCard,
    InsightCategory,
    RemarkableIndexEntry,
    SessionEventType,
    SessionMetrics,
    SessionRecord,
    SessionStatus,
    WeekRollup,
)


def _local_dt(value: datetime) -> datetime:
    return value.astimezone()


def _local_date_key(value: datetime) -> str:
    return _local_dt(value).date().isoformat()


def _week_start(value: datetime) -> datetime:
    local = _local_dt(value)
    return (local - timedelta(days=local.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)


def _week_id(value: datetime) -> str:
    start = _week_start(value)
    year, week, _ = start.isocalendar()
    return f"{year}-W{week:02d}"


def confidence_for_sample_size(sample_size: int) -> ConfidenceBucket:
    if sample_size >= 8:
        return ConfidenceBucket.HIGH
    if sample_size >= 4:
        return ConfidenceBucket.MEDIUM
    return ConfidenceBucket.LOW


def _active_intervals(session: SessionRecord) -> list[tuple[datetime, datetime]]:
    events = sorted(
        [
            event
            for event in session.event_history
            if event.type
            in {
                SessionEventType.SESSION_STARTED,
                SessionEventType.SESSION_RESUMED,
                SessionEventType.SESSION_PAUSED,
                SessionEventType.SESSION_STOPPED,
            }
        ],
        key=lambda event: event.timestamp,
    )
    intervals: list[tuple[datetime, datetime]] = []
    active_start: datetime | None = None

    for event in events:
        if event.type in {SessionEventType.SESSION_STARTED, SessionEventType.SESSION_RESUMED}:
            if active_start is None:
                active_start = event.timestamp
        elif active_start is not None:
            intervals.append((active_start, event.timestamp))
            active_start = None

    if active_start is not None and session.status == SessionStatus.RUNNING:
        end_time = session.last_review_at or session.updated_at
        intervals.append((active_start, end_time))

    if not intervals and session.status == SessionStatus.STOPPED and session.review_history:
        intervals.append((session.created_at, session.updated_at))

    return [(start, end) for start, end in intervals if end > start]


def _visible_transitions(session: SessionRecord) -> list[tuple[datetime, FocusLabel]]:
    transitions = sorted(
        [
            (event.timestamp, event.label)
            for event in session.event_history
            if event.type == SessionEventType.LABEL_TRANSITION and event.label is not None
        ],
        key=lambda item: item[0],
    )
    return transitions


def compute_session_metrics(session: SessionRecord) -> SessionMetrics:
    intervals = _active_intervals(session)
    if not intervals:
        return SessionMetrics(context_capture_count=len(session.context_history))

    transitions = _visible_transitions(session)
    start_time = intervals[0][0]

    focused_ms = 0
    drifting_ms = 0
    distracted_ms = 0
    away_ms = 0
    longest_focus_streak_ms = 0
    label_transition_count = len(transitions)

    first_drift_ms: int | None = None
    first_distraction_ms: int | None = None
    drift_count = 0
    distraction_count = 0
    away_count = 0
    recovery_count = 0
    recovery_durations: list[int] = []
    break_started_at: datetime | None = None

    for transition_time, label in transitions:
        if label == FocusLabel.DRIFTING:
            drift_count += 1
            if first_drift_ms is None:
                first_drift_ms = int((transition_time - start_time).total_seconds() * 1000)
        elif label == FocusLabel.DISTRACTED:
            distraction_count += 1
            if first_distraction_ms is None:
                first_distraction_ms = int((transition_time - start_time).total_seconds() * 1000)
        elif label == FocusLabel.AWAY:
            away_count += 1

        if label != FocusLabel.FOCUSED and break_started_at is None:
            break_started_at = transition_time
        if label == FocusLabel.FOCUSED and break_started_at is not None:
            recovery_count += 1
            recovery_durations.append(int((transition_time - break_started_at).total_seconds() * 1000))
            break_started_at = None

    for interval_start, interval_end in intervals:
        current_label = FocusLabel.FOCUSED
        for transition_time, label in transitions:
            if transition_time <= interval_start:
                current_label = label
            else:
                break

        segment_start = interval_start
        for transition_time, label in transitions:
            if transition_time <= interval_start:
                continue
            if transition_time >= interval_end:
                break
            duration_ms = int((transition_time - segment_start).total_seconds() * 1000)
            if current_label == FocusLabel.FOCUSED:
                focused_ms += duration_ms
                longest_focus_streak_ms = max(longest_focus_streak_ms, duration_ms)
            elif current_label == FocusLabel.DRIFTING:
                drifting_ms += duration_ms
            elif current_label == FocusLabel.DISTRACTED:
                distracted_ms += duration_ms
            else:
                away_ms += duration_ms
            current_label = label
            segment_start = transition_time

        duration_ms = int((interval_end - segment_start).total_seconds() * 1000)
        if current_label == FocusLabel.FOCUSED:
            focused_ms += duration_ms
            longest_focus_streak_ms = max(longest_focus_streak_ms, duration_ms)
        elif current_label == FocusLabel.DRIFTING:
            drifting_ms += duration_ms
        elif current_label == FocusLabel.DISTRACTED:
            distracted_ms += duration_ms
        else:
            away_ms += duration_ms

    session_length_ms = focused_ms + drifting_ms + distracted_ms + away_ms
    unfocused_ms = drifting_ms + distracted_ms + away_ms
    focus_ratio = (focused_ms / session_length_ms) if session_length_ms else 0.0
    session_hours = max(session_length_ms / 3_600_000, 0.001)
    interruption_count = drift_count + distraction_count + away_count

    nudge_events = [
        event for event in session.event_history if event.type == SessionEventType.NUDGE_SENT
    ]
    nudge_count = len(nudge_events)
    effective_nudges = 0
    focused_transition_times = [timestamp for timestamp, label in transitions if label == FocusLabel.FOCUSED]
    for event in nudge_events:
        if any(0 <= (focused_at - event.timestamp).total_seconds() <= 300 for focused_at in focused_transition_times):
            effective_nudges += 1

    transition_rate = label_transition_count / session_hours
    focus_stability = max(0.0, min(1.0, focus_ratio - min(transition_rate / 20.0, 0.45)))

    return SessionMetrics(
        session_length_ms=session_length_ms,
        focused_ms=focused_ms,
        unfocused_ms=unfocused_ms,
        drifting_ms=drifting_ms,
        distracted_ms=distracted_ms,
        away_ms=away_ms,
        focus_ratio=round(focus_ratio, 3),
        longest_focus_streak_ms=longest_focus_streak_ms,
        time_to_first_drift_ms=first_drift_ms,
        time_to_first_distraction_ms=first_distraction_ms,
        drift_count=drift_count,
        distraction_count=distraction_count,
        away_count=away_count,
        recovery_count=recovery_count,
        avg_recovery_ms=round(mean(recovery_durations), 2) if recovery_durations else None,
        nudge_count=nudge_count,
        nudge_effective_count=effective_nudges,
        nudge_effectiveness_rate=round((effective_nudges / nudge_count), 3) if nudge_count else 0.0,
        focus_stability_score=round(focus_stability, 3),
        interruption_density=round(interruption_count / session_hours, 3),
        label_transition_count=label_transition_count,
        context_capture_count=len(session.context_history),
    )


def build_session_insights(session: SessionRecord) -> list[InsightCard]:
    metrics = session.metrics
    insights: list[InsightCard] = []
    sample_size = max(metrics.label_transition_count, session.summary.total_reviews)

    if session.summary.total_reviews < 4:
        return [
            InsightCard(
                category=InsightCategory.PATTERN,
                title="Need more evidence",
                summary="This session is too short for strong conclusions. A few longer sessions will unlock better pattern detection.",
                confidence=ConfidenceBucket.LOW,
                sample_size=session.summary.total_reviews,
                supporting_metrics={"total_reviews": session.summary.total_reviews},
            )
        ]

    if metrics.longest_focus_streak_ms >= 20 * 60 * 1000:
        insights.append(
            InsightCard(
                category=InsightCategory.CONSISTENCY,
                title="Long focused stretch",
                summary="You held at least one solid stretch of focus without breaking the thread.",
                confidence=confidence_for_sample_size(sample_size),
                sample_size=sample_size,
                supporting_metrics={"longest_focus_streak_ms": metrics.longest_focus_streak_ms},
            )
        )

    if metrics.distraction_count > metrics.drift_count and metrics.distraction_count > 0:
        insights.append(
            InsightCard(
                category=InsightCategory.TRIGGER,
                title="Hard distractions dominated",
                summary="This session broke down more through clear distractions than soft drifting, which suggests a more obvious trigger was present.",
                confidence=confidence_for_sample_size(sample_size),
                sample_size=sample_size,
                supporting_metrics={
                    "distraction_count": metrics.distraction_count,
                    "drift_count": metrics.drift_count,
                },
            )
        )

    if metrics.recovery_count > 0 and metrics.avg_recovery_ms is not None:
        insights.append(
            InsightCard(
                category=InsightCategory.RECOVERY,
                title="Recovery pattern detected",
                summary="You were able to come back after losing the thread, which is often more important than never drifting at all.",
                confidence=confidence_for_sample_size(metrics.recovery_count),
                sample_size=metrics.recovery_count,
                supporting_metrics={"avg_recovery_ms": metrics.avg_recovery_ms},
            )
        )

    if metrics.nudge_count > 0:
        insights.append(
            InsightCard(
                category=InsightCategory.RECOVERY,
                title="Nudges had mixed value" if metrics.nudge_effectiveness_rate < 0.5 else "Nudges often helped",
                summary=(
                    "Live nudges did not reliably pull you back in this session."
                    if metrics.nudge_effectiveness_rate < 0.5
                    else "Live nudges often coincided with a recovery back into focus."
                ),
                confidence=confidence_for_sample_size(metrics.nudge_count),
                sample_size=metrics.nudge_count,
                supporting_metrics={
                    "nudge_count": metrics.nudge_count,
                    "nudge_effectiveness_rate": metrics.nudge_effectiveness_rate,
                },
            )
        )

    if not insights:
        insights.append(
            InsightCard(
                category=InsightCategory.PATTERN,
                title="Balanced session",
                summary="This session stayed relatively even without one extreme pattern overpowering everything else.",
                confidence=confidence_for_sample_size(sample_size),
                sample_size=sample_size,
                supporting_metrics={"focus_ratio": metrics.focus_ratio},
            )
        )

    return insights[:4]


def _session_dimension_values(session: SessionRecord) -> dict[str, str | None]:
    contexts = session.context_history
    manual_tags = session.config.manual_tags

    def most_common(values: list[str | None]) -> str | None:
        filtered = [value for value in values if value]
        if not filtered:
            return None
        return Counter(filtered).most_common(1)[0][0]

    time_of_day_hour = _local_dt(session.created_at).hour
    if 5 <= time_of_day_hour < 12:
        time_of_day = "morning"
    elif 12 <= time_of_day_hour < 17:
        time_of_day = "afternoon"
    elif 17 <= time_of_day_hour < 22:
        time_of_day = "evening"
    else:
        time_of_day = "night"

    phone_values: list[str | None] = []
    for context in contexts:
        if context.phone_present is not None:
            phone_values.append("phone_nearby" if context.phone_present else "phone_away")
    if manual_tags.phone_present is not None:
        phone_values.append("phone_nearby" if manual_tags.phone_present else "phone_away")

    return {
        "time_of_day": time_of_day,
        "day_of_week": _local_dt(session.created_at).strftime("%A"),
        "location_label": manual_tags.location_label or most_common([context.location_label for context in contexts]),
        "task": manual_tags.task or most_common([context.manual_tags.task for context in contexts]),
        "sound_bucket": most_common([context.sound_bucket for context in contexts]),
        "app_category": most_common([context.app_category for context in contexts]),
        "phone_present": most_common(phone_values),
    }


def build_experiment_dimensions(sessions: list[SessionRecord]) -> list[ExperimentDimensionView]:
    aggregations: dict[str, dict[str, list[SessionRecord]]] = defaultdict(lambda: defaultdict(list))
    for session in sessions:
        if session.metrics.session_length_ms <= 0:
            continue
        for dimension, value in _session_dimension_values(session).items():
            if value:
                aggregations[dimension][value].append(session)

    dimensions: list[ExperimentDimensionView] = []
    for dimension, groups in aggregations.items():
        comparisons: list[ComparisonPoint] = []
        for key, group_sessions in groups.items():
            focus_ratios = [candidate.metrics.focus_ratio for candidate in group_sessions]
            recovery_values = [
                candidate.metrics.avg_recovery_ms
                for candidate in group_sessions
                if candidate.metrics.avg_recovery_ms is not None
            ]
            comparisons.append(
                ComparisonPoint(
                    dimension=dimension,
                    key=key,
                    sample_size=len(group_sessions),
                    session_count=len(group_sessions),
                    avg_focus_ratio=round(mean(focus_ratios), 3),
                    avg_recovery_ms=round(mean(recovery_values), 2) if recovery_values else None,
                    avg_session_length_ms=round(
                        mean(candidate.metrics.session_length_ms for candidate in group_sessions), 2
                    ),
                    confidence=confidence_for_sample_size(len(group_sessions)),
                )
            )
        if comparisons:
            comparisons.sort(key=lambda item: item.avg_focus_ratio, reverse=True)
            dimensions.append(
                ExperimentDimensionView(
                    dimension=dimension,
                    comparisons=comparisons,
                )
            )

    dimensions.sort(key=lambda item: item.dimension)
    return dimensions


def build_experiment_view(sessions: list[SessionRecord]) -> ExperimentComparisonView:
    dimensions = build_experiment_dimensions(sessions)
    insight_cards: list[InsightCard] = []
    for dimension_view in dimensions:
        if len(dimension_view.comparisons) < 2:
            continue
        best = dimension_view.comparisons[0]
        worst = dimension_view.comparisons[-1]
        if best.avg_focus_ratio - worst.avg_focus_ratio < 0.08:
            continue
        insight_cards.append(
            InsightCard(
                category=InsightCategory.EXPERIMENT_RESULT,
                title=f"{dimension_view.dimension.replace('_', ' ').title()} matters",
                summary=f"{best.key} is currently outperforming {worst.key} on focus ratio in your local data.",
                confidence=min(best.confidence, worst.confidence, key=lambda bucket: bucket.value),
                sample_size=min(best.sample_size, worst.sample_size),
                supporting_metrics={
                    "dimension": dimension_view.dimension,
                    "best_focus_ratio": best.avg_focus_ratio,
                    "worst_focus_ratio": worst.avg_focus_ratio,
                },
            )
        )

    return ExperimentComparisonView(dimensions=dimensions, insights=insight_cards[:4])


def _hour_blocks(sessions: list[SessionRecord]) -> tuple[list[HourBlock], list[HourBlock]]:
    counts: dict[int, list[int]] = defaultdict(list)
    for session in sessions:
        for review in session.review_history:
            hour = _local_dt(review.timestamp).hour
            counts[hour].append(1 if review.label == FocusLabel.FOCUSED else 0)

    blocks = [
        HourBlock(hour=hour, sample_size=len(values), focus_ratio=round(sum(values) / len(values), 3))
        for hour, values in counts.items()
        if values
    ]
    best = sorted(blocks, key=lambda block: (block.focus_ratio, block.sample_size), reverse=True)[:3]
    worst = sorted(blocks, key=lambda block: (block.focus_ratio, -block.sample_size))[:3]
    return best, worst


def build_day_rollup(date_key: str, sessions: list[SessionRecord]) -> DayRollup:
    focus_ratios = [session.metrics.focus_ratio for session in sessions if session.metrics.session_length_ms > 0]
    recovery_values = [
        session.metrics.avg_recovery_ms for session in sessions if session.metrics.avg_recovery_ms is not None
    ]
    best_hours, worst_hours = _hour_blocks(sessions)
    experiment_view = build_experiment_view(sessions)
    top_contexts = [
        comparison
        for dimension in experiment_view.dimensions
        for comparison in dimension.comparisons[:1]
    ][:5]

    rollup = DayRollup(
        date=date_key,
        session_count=len(sessions),
        total_focused_ms=sum(session.metrics.focused_ms for session in sessions),
        total_unfocused_ms=sum(session.metrics.unfocused_ms for session in sessions),
        avg_focus_ratio=round(mean(focus_ratios), 3) if focus_ratios else 0.0,
        avg_recovery_ms=round(mean(recovery_values), 2) if recovery_values else None,
        best_hour_blocks=best_hours,
        worst_hour_blocks=worst_hours,
        top_contexts=top_contexts,
    )

    if rollup.session_count == 0:
        rollup.insights = [
            InsightCard(
                category=InsightCategory.PATTERN,
                title="No sessions yet",
                summary="Start a few sessions and Focus Buddy will begin surfacing daily patterns here.",
                confidence=ConfidenceBucket.LOW,
                sample_size=0,
            )
        ]
    elif rollup.best_hour_blocks:
        rollup.insights = [
            InsightCard(
                category=InsightCategory.CONSISTENCY,
                title="Best time block today",
                summary=f"Your strongest block today was around {rollup.best_hour_blocks[0].hour}:00.",
                confidence=confidence_for_sample_size(rollup.best_hour_blocks[0].sample_size),
                sample_size=rollup.best_hour_blocks[0].sample_size,
                supporting_metrics={"focus_ratio": rollup.best_hour_blocks[0].focus_ratio},
            )
        ]

    return rollup


def build_week_rollup(reference: datetime, sessions: list[SessionRecord], all_sessions: list[SessionRecord]) -> WeekRollup:
    week_start = _week_start(reference)
    week_end = week_start + timedelta(days=7)

    focus_ratios = [session.metrics.focus_ratio for session in sessions if session.metrics.session_length_ms > 0]
    recovery_values = [
        session.metrics.avg_recovery_ms for session in sessions if session.metrics.avg_recovery_ms is not None
    ]
    experiment_view = build_experiment_view(sessions)
    best_conditions: list[ComparisonPoint] = []
    weakest_conditions: list[ComparisonPoint] = []
    for dimension in experiment_view.dimensions:
        if dimension.comparisons:
            best_conditions.append(dimension.comparisons[0])
            weakest_conditions.append(dimension.comparisons[-1])

    prior_start = week_start - timedelta(days=7)
    prior_sessions = [
        session
        for session in all_sessions
        if prior_start.date() <= _local_dt(session.created_at).date() < week_start.date()
        and session.metrics.session_length_ms > 0
    ]
    prior_focus = [session.metrics.focus_ratio for session in prior_sessions]
    consistency_delta = None
    if focus_ratios and prior_focus:
        consistency_delta = round(mean(focus_ratios) - mean(prior_focus), 3)

    rollup = WeekRollup(
        week_id=_week_id(reference),
        week_start=week_start.date().isoformat(),
        week_end=(week_end - timedelta(days=1)).date().isoformat(),
        session_count=len(sessions),
        avg_focus_ratio=round(mean(focus_ratios), 3) if focus_ratios else 0.0,
        avg_recovery_ms=round(mean(recovery_values), 2) if recovery_values else None,
        consistency_delta=consistency_delta,
        best_conditions=sorted(best_conditions, key=lambda item: item.avg_focus_ratio, reverse=True)[:5],
        weakest_conditions=sorted(weakest_conditions, key=lambda item: item.avg_focus_ratio)[:5],
    )

    if rollup.session_count == 0:
        rollup.insights = [
            InsightCard(
                category=InsightCategory.PATTERN,
                title="No weekly data yet",
                summary="This week needs more sessions before Focus Buddy can say anything useful.",
                confidence=ConfidenceBucket.LOW,
                sample_size=0,
            )
        ]
    else:
        summaries: list[InsightCard] = []
        if rollup.consistency_delta is not None:
            summaries.append(
                InsightCard(
                    category=InsightCategory.CONSISTENCY,
                    title="Weekly consistency moved",
                    summary=(
                        "Your average focus ratio improved versus last week."
                        if rollup.consistency_delta > 0
                        else "Your average focus ratio slipped versus last week."
                    ),
                    confidence=confidence_for_sample_size(rollup.session_count),
                    sample_size=rollup.session_count,
                    supporting_metrics={"consistency_delta": rollup.consistency_delta},
                )
            )
        if rollup.best_conditions:
            best = rollup.best_conditions[0]
            summaries.append(
                InsightCard(
                    category=InsightCategory.ENVIRONMENT,
                    title="Strongest weekly condition",
                    summary=f"{best.key} produced the strongest focus ratio in this week's local data.",
                    confidence=best.confidence,
                    sample_size=best.sample_size,
                    supporting_metrics={"dimension": best.dimension, "avg_focus_ratio": best.avg_focus_ratio},
                )
            )
        rollup.insights = summaries[:4]

    return rollup


def build_today_and_week(sessions: list[SessionRecord], reference: datetime | None = None) -> tuple[DayRollup, WeekRollup]:
    now = reference or datetime.now().astimezone()
    today_key = now.date().isoformat()
    today_sessions = [
        session for session in sessions if _local_date_key(session.created_at) == today_key
    ]
    day_rollup = build_day_rollup(today_key, today_sessions)

    week_start = _week_start(now)
    week_sessions = [
        session
        for session in sessions
        if week_start.date() <= _local_dt(session.created_at).date() < (week_start + timedelta(days=7)).date()
    ]
    week_rollup = build_week_rollup(now, week_sessions, sessions)
    return day_rollup, week_rollup


def build_remarkable_index(sessions: list[SessionRecord]) -> list[RemarkableIndexEntry]:
    entries: list[RemarkableIndexEntry] = []
    for session in sessions:
        if session.remarkable:
            session_note = next(
                (moment.note for moment in session.remarkable_moments if moment.session_level and moment.note),
                None,
            )
            entries.append(
                RemarkableIndexEntry(
                    session_id=session.id,
                    session_name=session.config.session_name,
                    created_at=session.created_at,
                    session_level=True,
                    note=session_note,
                )
            )
        for moment in session.remarkable_moments:
            if moment.session_level:
                continue
            entries.append(
                RemarkableIndexEntry(
                    session_id=session.id,
                    session_name=session.config.session_name,
                    created_at=session.created_at,
                    sequence=moment.sequence,
                    note=moment.note,
                    keyframe_path=moment.keyframe_path,
                )
            )
    entries.sort(key=lambda entry: entry.created_at, reverse=True)
    return entries
