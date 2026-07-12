"""Deterministic structural patching for pinned TripSnapshot replans."""

from __future__ import annotations

import hashlib

from routepilot_contracts.artifacts import ConstraintSpec, TravelPreference, TripBrief
from routepilot_contracts.common import ActorRef, MoneyRange, TripDateRange

from .models import Principal, ReplanPatch, new_public_id, utc_now


def _actor(principal: Principal) -> ActorRef:
    digest = hashlib.sha256(principal.user_id.encode("utf-8")).hexdigest()[:32]
    return ActorRef(actor_type="user", actor_id=f"user:{digest}")


def apply_replan_patch(
    brief: TripBrief,
    patch: ReplanPatch,
    *,
    principal: Principal,
) -> TripBrief:
    """Create a new TripBrief while preserving every unmodified base constraint."""

    now = utc_now()
    date_window = brief.date_window
    budget = brief.budget
    preferences = list(brief.preferences)
    constraints = list(brief.constraints)

    if patch.dates is not None:
        date_window = TripDateRange(
            start_date=patch.dates.start_date,
            end_date=patch.dates.end_date,
            timezone=brief.date_window.timezone,
        )
        constraints = [item for item in constraints if item.constraint_type != "date"]
        constraints.append(
            ConstraintSpec(
                constraint_id=new_public_id("constraint"),
                constraint_type="date",
                hard=True,
                priority=5,
                description=(
                    f"旅行日期为 {patch.dates.start_date.isoformat()} 至 "
                    f"{patch.dates.end_date.isoformat()}。"
                ),
                source=brief.source,
            )
        )

    if patch.budget is not None:
        budget = MoneyRange(
            min_amount=patch.budget.min_amount,
            max_amount=patch.budget.max_amount,
            currency=patch.budget.currency or brief.budget.currency,
            basis=brief.budget.basis,
            observed_at=now,
            source=brief.source,
        )
        constraints = [item for item in constraints if item.constraint_type != "budget"]
        constraints.append(
            ConstraintSpec(
                constraint_id=new_public_id("constraint"),
                constraint_type="budget",
                hard=True,
                priority=5,
                description=(
                    f"总预算为 {budget.min_amount}–{budget.max_amount} {budget.currency}。"
                ),
                source=brief.source,
            )
        )

    if patch.preferences is not None:
        removed = {value.casefold() for value in patch.preferences.remove}
        preferences = [item for item in preferences if item.value.casefold() not in removed]
        known = {item.value.casefold() for item in preferences}
        for value in patch.preferences.add:
            if value.casefold() in known:
                continue
            preferences.append(
                TravelPreference(
                    preference_id=new_public_id("preference"),
                    category="other",
                    value=value,
                    priority=3,
                )
            )
            known.add(value.casefold())

    existing_descriptions = {item.description.casefold() for item in constraints}
    for place in patch.exclude_places:
        description = place
        if description.casefold() not in existing_descriptions:
            constraints.append(
                ConstraintSpec(
                    constraint_id=new_public_id("constraint"),
                    constraint_type="avoid",
                    hard=True,
                    priority=5,
                    description=description,
                    source=brief.source,
                )
            )
            existing_descriptions.add(description.casefold())
    for place in patch.retain_places:
        description = place
        if description.casefold() not in existing_descriptions:
            constraints.append(
                ConstraintSpec(
                    constraint_id=new_public_id("constraint"),
                    constraint_type="visit",
                    hard=True,
                    priority=5,
                    description=description,
                    source=brief.source,
                )
            )
            existing_descriptions.add(description.casefold())

    return brief.model_copy(
        update={
            "artifact_id": new_public_id("artifact"),
            "version": 1,
            "created_at": now,
            "created_by": _actor(principal),
            "reason": "基于固定版本 TripSnapshot 应用用户确认的结构化重规划补丁。",
            "date_window": date_window,
            "budget": budget,
            "preferences": preferences,
            "constraints": constraints,
        }
    )


__all__ = ["apply_replan_patch"]
