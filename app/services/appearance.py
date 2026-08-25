"""Shared appearance choices and safe defaults."""

PAGE_TRANSITION_CHOICES = (
    ("stretch", "左侧拉伸"),
    ("fade", "直接浮现"),
    ("zoom-blur", "缩放与模糊"),
    ("none", "无动画"),
)
PAGE_TRANSITION_VALUES = frozenset(value for value, _label in PAGE_TRANSITION_CHOICES)
PAGE_TRANSITION_COLOR_DEFAULTS = {
    "page_transition_color_start": "#eaf6ff",
    "page_transition_color_middle": "#f9fbff",
    "page_transition_color_end": "#fceef6",
}

DIALOG_STYLE_CHOICES = (
    ("soft", "柔和圆角"),
    ("glass", "轻透玻璃"),
    ("paper", "纸张卡片"),
    ("compact", "紧凑浮层"),
    ("cloud", "柔和气泡"),
    ("outline", "轻线留白"),
)
DIALOG_STYLE_VALUES = frozenset(value for value, _label in DIALOG_STYLE_CHOICES)
DIALOG_SHADOW_CHOICES = (
    ("none", "无阴影"),
    ("light", "轻柔"),
    ("soft", "标准"),
    ("deep", "深层悬浮"),
)
DIALOG_SHADOW_VALUES = frozenset(value for value, _label in DIALOG_SHADOW_CHOICES)
DIALOG_APPEARANCE_DEFAULTS = {
    "dialog_style": "soft",
    "dialog_color_start": "#ffffff",
    "dialog_color_end": "#fff1f7",
    "dialog_accent": "#7eaed0",
    "dialog_radius": "30",
    "dialog_width": "510",
    "dialog_backdrop_blur": "6",
    "dialog_shadow": "soft",
}
