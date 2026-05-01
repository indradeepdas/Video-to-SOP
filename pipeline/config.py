from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from typing import Any

from pipeline.runtime_config import get_config


@dataclass(frozen=True)
class QualityProfile:
    name: str
    metric_interval_seconds: float
    max_metric_frames: int
    frame_interval_seconds: float
    max_extracted_frames: int
    max_selected_frames: int
    max_ocr_frames: int
    max_events: int
    max_steps: int
    batch_size: int
    max_gpt_calls: int
    verify_risky_limit: int
    include_context_images: bool
    ambiguous_boundary_reviews: int
    max_segment_duration_seconds: float
    target_event_density: float


PROFILES: dict[str, QualityProfile] = {
    "Showcase fast": QualityProfile(
        name="Showcase fast",
        metric_interval_seconds=1.25,
        max_metric_frames=650,
        frame_interval_seconds=5.0,
        max_extracted_frames=650,
        max_selected_frames=60,
        max_ocr_frames=30,
        max_events=36,
        max_steps=40,
        batch_size=12,
        max_gpt_calls=4,
        verify_risky_limit=8,
        include_context_images=False,
        ambiguous_boundary_reviews=0,
        max_segment_duration_seconds=30.0,
        target_event_density=3.0,
    ),
    "Balanced": QualityProfile(
        name="Balanced",
        metric_interval_seconds=1.0,
        max_metric_frames=2800,
        frame_interval_seconds=4.5,
        max_extracted_frames=850,
        max_selected_frames=80,
        max_ocr_frames=60,
        max_events=40,
        max_steps=40,
        batch_size=9,
        max_gpt_calls=6,
        verify_risky_limit=24,
        include_context_images=True,
        ambiguous_boundary_reviews=8,
        max_segment_duration_seconds=30.0,
        target_event_density=3.0,
    ),
    "Lowest cost": QualityProfile(
        name="Lowest cost",
        metric_interval_seconds=2.0,
        max_metric_frames=1400,
        frame_interval_seconds=6.0,
        max_extracted_frames=500,
        max_selected_frames=50,
        max_ocr_frames=40,
        max_events=28,
        max_steps=30,
        batch_size=10,
        max_gpt_calls=4,
        verify_risky_limit=12,
        include_context_images=False,
        ambiguous_boundary_reviews=0,
        max_segment_duration_seconds=45.0,
        target_event_density=2.0,
    ),
    "Highest accuracy": QualityProfile(
        name="Highest accuracy",
        metric_interval_seconds=1.0,
        max_metric_frames=3200,
        frame_interval_seconds=3.0,
        max_extracted_frames=950,
        max_selected_frames=110,
        max_ocr_frames=80,
        max_events=45,
        max_steps=40,
        batch_size=8,
        max_gpt_calls=8,
        verify_risky_limit=32,
        include_context_images=True,
        ambiguous_boundary_reviews=16,
        max_segment_duration_seconds=24.0,
        target_event_density=4.0,
    ),
}


DEFAULT_PROFILE = "Showcase fast"
DEFAULT_MODEL = "gpt-5.5"


def get_profile(name: str | None) -> QualityProfile:
    return PROFILES.get(name or DEFAULT_PROFILE, PROFILES[DEFAULT_PROFILE])


def profile_to_dict(profile: QualityProfile) -> dict[str, Any]:
    return asdict(profile)


def model_name() -> str:
    return get_config("OPENAI_MODEL", DEFAULT_MODEL) or DEFAULT_MODEL


def pricing_defaults() -> dict[str, float]:
    return {
        "input_per_million": float(get_config("VIDEO2SOP_INPUT_PRICE_PER_1M", "5.00") or "5.00"),
        "output_per_million": float(get_config("VIDEO2SOP_OUTPUT_PRICE_PER_1M", "30.00") or "30.00"),
        "low_detail_image_tokens": float(get_config("VIDEO2SOP_LOW_DETAIL_IMAGE_TOKENS", "85") or "85"),
        "text_input_tokens_per_event": float(get_config("VIDEO2SOP_TEXT_INPUT_TOKENS_PER_EVENT", "220") or "220"),
        "output_tokens_per_step": float(get_config("VIDEO2SOP_OUTPUT_TOKENS_PER_STEP", "90") or "90"),
        "fixed_prompt_tokens_per_call": float(get_config("VIDEO2SOP_FIXED_PROMPT_TOKENS_PER_CALL", "900") or "900"),
    }


def estimate_job_cost(profile: QualityProfile, use_openai: bool = True) -> dict[str, Any]:
    generation_calls = math.ceil(profile.max_events / profile.batch_size)
    verification_calls = 1 if profile.verify_risky_limit > 0 else 0
    boundary_review_calls = 1 if profile.ambiguous_boundary_reviews > 0 else 0
    calls = min(profile.max_gpt_calls, generation_calls + verification_calls + boundary_review_calls)

    reserved_calls = verification_calls + boundary_review_calls
    generation_call_budget = max(0, profile.max_gpt_calls - reserved_calls)
    generation_events = min(profile.max_events, profile.batch_size * min(generation_calls, generation_call_budget))
    generation_images = generation_events * (3 if profile.include_context_images else 1)
    verification_images = min(profile.verify_risky_limit, profile.max_events)
    boundary_images = min(profile.ambiguous_boundary_reviews * 2, profile.max_events * 2)
    image_count = generation_images + verification_images + boundary_images

    prices = pricing_defaults()
    input_tokens = (
        calls * prices["fixed_prompt_tokens_per_call"]
        + generation_events * prices["text_input_tokens_per_event"]
        + image_count * prices["low_detail_image_tokens"]
    )
    output_tokens = min(profile.max_steps, profile.max_events) * prices["output_tokens_per_step"]
    cost = 0.0
    if use_openai:
        cost = (input_tokens / 1_000_000 * prices["input_per_million"]) + (
            output_tokens / 1_000_000 * prices["output_per_million"]
        )

    return {
        "model": model_name(),
        "profile": profile.name,
        "max_calls": calls if use_openai else 0,
        "image_count": int(image_count if use_openai else 0),
        "input_tokens": int(input_tokens if use_openai else 0),
        "output_tokens": int(output_tokens if use_openai else 0),
        "estimated_cost_usd": round(cost, 4),
        "pricing_note": "Estimate uses configurable defaults, not exact billed usage.",
    }
