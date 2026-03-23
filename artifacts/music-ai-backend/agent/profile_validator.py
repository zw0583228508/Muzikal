from dataclasses import dataclass, field
from typing import Any

REQUIRED_ROLES = {"BASS", "RHYTHM_KICK", "MELODY_LEAD"}
VALID_ROLES = {
    "MELODY_LEAD", "MELODY_COUNTER", "HARMONY_CHORD", "HARMONY_PAD",
    "BASS", "RHYTHM_KICK", "RHYTHM_SNARE", "RHYTHM_PERC", "COLOR", "DRONE",
}
KNOWN_SCALE_TYPES = {
    "major", "minor", "harmonic_minor", "melodic_minor",
    "phrygian", "dorian", "mixolydian", "lydian", "locrian",
    "maqam_hijaz", "maqam_rast", "maqam_bayati", "maqam_nahawand",
    "maqam_kurd", "maqam_saba", "maqam_sigah",
    "freygish", "ahava_raba",
    "pentatonic_major", "pentatonic_minor",
    "blues", "whole_tone", "diminished",
    "pelog", "slendro",
    "carnatic_bilaval", "carnatic_bhairav",
    "generic",
}


class ValidationError(Exception):
    def __init__(self, errors: list[str]):
        self.errors = errors
        super().__init__("; ".join(errors))


@dataclass
class ValidationResult:
    valid: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


class ProfileValidator:
    """Validates a StyleProfile dict before arrangement generation."""

    def validate(self, profile: dict) -> ValidationResult:
        errors: list[str] = []
        warnings: list[str] = []

        instruments = profile.get("instruments", [])
        if not instruments:
            errors.append("instruments list is empty")
        else:
            present_roles = {inst.get("role", "") for inst in instruments}
            missing = REQUIRED_ROLES - present_roles
            if missing:
                errors.append(f"Missing required instrument roles: {missing}")

            for i, inst in enumerate(instruments):
                role = inst.get("role", "")
                if role not in VALID_ROLES:
                    errors.append(f"instruments[{i}].role '{role}' is not a valid InstrumentRole")
                midi = inst.get("midiProgram", -1)
                if not isinstance(midi, int) or not (0 <= midi <= 127):
                    errors.append(
                        f"instruments[{i}].midiProgram must be int 0-127, got {midi!r}"
                    )
                vol = inst.get("volumeWeight", 0)
                if not isinstance(vol, (int, float)) or not (0.0 <= vol <= 1.0):
                    errors.append(
                        f"instruments[{i}].volumeWeight must be 0.0-1.0, got {vol!r}"
                    )

            total_vol = sum(inst.get("volumeWeight", 0) for inst in instruments)
            if total_vol > 4.0:
                errors.append(
                    f"Sum of volumeWeight ({total_vol:.2f}) exceeds 4.0"
                )

        bpm = profile.get("bpmRange")
        if isinstance(bpm, (list, tuple)) and len(bpm) == 2:
            if bpm[0] >= bpm[1]:
                errors.append(
                    f"bpmRange[0] ({bpm[0]}) must be less than bpmRange[1] ({bpm[1]})"
                )
        elif bpm is not None:
            errors.append("bpmRange must be a list of [min, max]")

        scale = profile.get("scaleType", "")
        if scale and scale.lower() not in KNOWN_SCALE_TYPES:
            warnings.append(
                f"scaleType '{scale}' not in known list — will use generic fallback"
            )

        genre = profile.get("genre", "")
        if not genre:
            errors.append("genre is required")

        return ValidationResult(
            valid=len(errors) == 0,
            errors=errors,
            warnings=warnings,
        )

    def validate_or_raise(self, profile: dict) -> None:
        result = self.validate(profile)
        if not result.valid:
            raise ValidationError(result.errors)
