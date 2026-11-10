"""Class drivers: which stated attributes the classification depends on.

For every attribute that differs from its default, the device is
re-classified with that one attribute reset to the default. If the class
changes, that attribute is a driver of the result. This is a plain
one-at-a-time sensitivity check using the same engine, so it explains a
result in terms of the inputs ("without contact with the heart this
would be IIb") and shows which facts are worth double-checking first.
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass
from enum import Enum
from typing import Optional

from rules_engine.base import ClassificationEngine
from rules_engine.models import DeviceAttributes

_SKIP = {"name", "description"}


@dataclass
class ClassDriver:
    attribute: str
    value: object
    class_without: Optional[str]


def class_drivers(device: DeviceAttributes, engine: ClassificationEngine) -> list[ClassDriver]:
    baseline = engine.classify(device).device_class
    defaults = DeviceAttributes()
    drivers: list[ClassDriver] = []
    for f in dataclasses.fields(DeviceAttributes):
        if f.name in _SKIP:
            continue
        value = getattr(device, f.name)
        default = getattr(defaults, f.name)
        if value == default:
            continue
        variant = dataclasses.replace(device, **{f.name: default})
        other = engine.classify(variant).device_class
        if other != baseline:
            drivers.append(
                ClassDriver(
                    attribute=f.name,
                    value=value.value if isinstance(value, Enum) else value,
                    class_without=other.value if other else None,
                )
            )
    return drivers
