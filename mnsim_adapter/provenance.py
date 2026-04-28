"""
Provenance metadata for every field in a ChipProfile.

Taxonomy
--------
The ``kind`` field classifies how strongly a value is justified. This is
the first thing a reviewer (or future maintainer) looks at when auditing
whether a chip profile is honest or back-fit.

- physical  : constrained by physics or process (tech node, V_read, V_write).
- design    : architectural choice for this chip (xbar size, tile count).
- empirical : measured on a specific chip or dataset, cited source available.
- fitted    : tuned post-hoc to match a downstream observation. High risk.
- proxy     : deliberate stand-in because the real value is unavailable; must
              be labelled as such so downstream comparisons stay honest.
- missing   : no defensible value; field is unset. Consumer must either skip
              or refuse to run.

Anything marked ``fitted`` or ``proxy`` should show up in the
``to_mnsim_ini`` output as a visible comment so the generated config is
self-documenting.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Generic, TypeVar

VALID_KINDS = frozenset(
    {"physical", "design", "empirical", "fitted", "proxy", "missing"}
)


@dataclass(frozen=True)
class Provenance:
    """Where a profile field value comes from, and how much to trust it."""

    kind: str
    source: str = ""
    note: str = ""

    def __post_init__(self) -> None:
        if self.kind not in VALID_KINDS:
            raise ValueError(
                f"Provenance.kind must be one of {sorted(VALID_KINDS)}; "
                f"got {self.kind!r}"
            )


T = TypeVar("T")


@dataclass(frozen=True)
class Traced(Generic[T]):
    """A value paired with its Provenance."""

    value: T
    provenance: Provenance

    def is_missing(self) -> bool:
        return self.provenance.kind == "missing" or self.value is None

    def format_inline_comment(self) -> str:
        """Render a one-line comment suitable for an INI ``# ...`` annotation."""
        tag = f"[{self.provenance.kind}]"
        parts = [tag]
        if self.provenance.source:
            parts.append(self.provenance.source)
        if self.provenance.note:
            parts.append(f"— {self.provenance.note}")
        return " ".join(parts)
