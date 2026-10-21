"""Validated tag colors and contrast-aware foreground selection."""
import secrets
import re

PALETTE = ('#c4b5fd', '#a7f3d0', '#bae6fd', '#fde68a', '#fecdd3', '#fed7aa', '#c7d2fe', '#99f6e4')


def random_color():
    return secrets.choice(PALETTE)


def valid_color(value):
    return isinstance(value, str) and re.fullmatch(r'#[0-9a-fA-F]{6}', value) is not None


def foreground(color):
    def linear(value):
        value = int(value, 16) / 255
        return value / 12.92 if value <= 0.04045 else ((value + 0.055) / 1.055) ** 2.4
    luminance = sum(linear(color[i:i+2]) * weight for i, weight in [(1, .2126), (3, .7152), (5, .0722)])
    return '#000000' if luminance > .179 else '#ffffff'
