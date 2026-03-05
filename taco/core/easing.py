import math


def quint_ease_in(t: float, b: float, c: float, d: float) -> float:
    """Quintic (t^5) easing in: accelerating from zero velocity.
    t=current time, b=start value, c=change in value, d=duration."""
    if d == 0:
        return b
    t = t / d
    return c * t * t * t * t * t + b


def quint_ease_out(t: float, b: float, c: float, d: float) -> float:
    """Quintic (t^5) easing out: decelerating from zero velocity."""
    if d == 0:
        return b + c
    t = t / d - 1
    return c * (t * t * t * t * t + 1) + b


def quint_ease_in_out(t: float, b: float, c: float, d: float) -> float:
    """Quintic (t^5) easing in/out: acceleration until halfway, then deceleration."""
    if d == 0:
        return b + c
    t = t / (d / 2)
    if t < 1:
        return c / 2 * t * t * t * t * t + b
    t -= 2
    return c / 2 * (t * t * t * t * t + 2) + b


def linear(t: float, b: float, c: float, d: float) -> float:
    if d == 0:
        return b + c
    return c * t / d + b
