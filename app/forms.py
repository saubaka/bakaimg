"""Forms for phase-two identity and administration."""

from flask_wtf import FlaskForm
from flask_wtf.file import MultipleFileField
from wtforms import (
    BooleanField,
    IntegerField,
    PasswordField,
    RadioField,
    SelectField,
    SelectMultipleField,
    StringField,
    SubmitField,
    TextAreaField,
)
from wtforms.validators import DataRequired, EqualTo, Length, NumberRange, Optional, Regexp

HEX_COLOR_VALIDATORS = [
    DataRequired(),
    Regexp(r"^#[0-9A-Fa-f]{6}$", message="请选择六位颜色值。"),
]


class GatewayConnectionForm(FlaskForm):
    issuer = StringField("发行者地址", validators=[DataRequired(), Length(max=500)])
    client_id = StringField("Client ID", validators=[DataRequired(), Length(max=200)])
    client_secret = PasswordField(
        "Client Secret",
        validators=[Optional(), Length(min=8, max=512)],
    )
    submit = SubmitField("保存并验证连接")


class LocalAdminSetupForm(FlaskForm):
    username = StringField("管理员用户名", validators=[DataRequired(), Length(min=3, max=50)])
    email = StringField("管理员邮箱", validators=[DataRequired(), Length(max=254)])
    display_name = StringField("显示名称", validators=[DataRequired(), Length(min=1, max=80)])
    password = PasswordField("管理员密码", validators=[DataRequired(), Length(min=12, max=256)])
    confirm_password = PasswordField(
        "确认管理员密码",
        validators=[DataRequired(), EqualTo("password", message="两次输入的密码不一致。")],
    )
    submit = SubmitField("创建首位超级管理员")


class UserAdminForm(FlaskForm):
    display_name = StringField("显示名称", validators=[DataRequired(), Length(max=80)])
    email = StringField("电子邮箱", validators=[DataRequired(), Length(max=254)])
    status = StringField("状态", validators=[DataRequired(), Length(max=20)])
    role_ids = SelectMultipleField("角色", coerce=int, validators=[Optional()])
    storage_quota_mb = IntegerField(
        "存储配额（MiB）",
        validators=[DataRequired(), NumberRange(min=16, max=1_048_576)],
    )
    image_quota_count = IntegerField(
        "图片数量配额",
        validators=[DataRequired(), NumberRange(min=1, max=1_000_000)],
    )
    submit = SubmitField("保存账号")


class RoleForm(FlaskForm):
    name = StringField("角色名称", validators=[DataRequired(), Length(max=80)])
    description = StringField("说明", validators=[Optional(), Length(max=255)])
    permission_ids = SelectMultipleField("权限", coerce=int, validators=[Optional()])
    submit = SubmitField("保存角色")


class MaintenanceForm(FlaskForm):
    enabled = BooleanField("开启维护模式")
    message = StringField(
        "访客提示",
        validators=[DataRequired(), Length(min=1, max=160)],
    )
    submit = SubmitField("保存维护状态")


class EmptyForm(FlaskForm):
    submit = SubmitField("确认")


class TransitionSettingsForm(FlaskForm):
    transition_style = RadioField("页面过渡方式", validators=[DataRequired()])
    transition_duration = IntegerField(
        "动画时间（毫秒）", validators=[DataRequired(), NumberRange(min=300, max=2400)]
    )
    transition_color_start = StringField("覆盖起始色", validators=HEX_COLOR_VALIDATORS)
    transition_color_middle = StringField("覆盖过渡色", validators=HEX_COLOR_VALIDATORS)
    transition_color_end = StringField("覆盖结束色", validators=HEX_COLOR_VALIDATORS)
    submit = SubmitField("保存动效设置")


class DialogAppearanceForm(FlaskForm):
    dialog_style = RadioField("弹窗样式", validators=[DataRequired()])
    dialog_color_start = StringField("弹窗起始色", validators=HEX_COLOR_VALIDATORS)
    dialog_color_end = StringField("弹窗结束色", validators=HEX_COLOR_VALIDATORS)
    dialog_accent = StringField("弹窗强调色", validators=HEX_COLOR_VALIDATORS)
    dialog_radius = IntegerField(
        "弹窗圆角", validators=[DataRequired(), NumberRange(min=14, max=42)]
    )
    dialog_width = IntegerField(
        "弹窗宽度", validators=[DataRequired(), NumberRange(min=360, max=720)]
    )
    dialog_backdrop_blur = IntegerField(
        "背景模糊", validators=[DataRequired(), NumberRange(min=0, max=30)]
    )
    dialog_shadow = RadioField("阴影强度", validators=[DataRequired()])
    submit = SubmitField("保存弹窗外观")


class ImageUploadForm(FlaskForm):
    images = MultipleFileField("选择图片", validators=[DataRequired()])
    visibility = SelectField(
        "访问方式",
        choices=[
            ("private", "仅自己可见"),
            ("unlisted", "通过链接分享"),
            ("public", "公开展示"),
        ],
        validators=[DataRequired()],
    )
    submit = SubmitField("确定上传")


class ImageEditForm(FlaskForm):
    title = StringField("图片标题", validators=[Optional(), Length(max=160)])
    alt_text = TextAreaField("图片说明", validators=[Optional(), Length(max=240)])
    visibility = SelectField(
        "访问方式",
        choices=[
            ("private", "仅自己可见"),
            ("unlisted", "通过链接分享"),
            ("public", "公开展示"),
        ],
        validators=[DataRequired()],
    )
    submit = SubmitField("保存图片信息")


class AlbumForm(FlaskForm):
    title = StringField("相册名称", validators=[DataRequired(), Length(max=120)])
    description = TextAreaField("相册介绍", validators=[Optional(), Length(max=500)])
    visibility = SelectField(
        "访问方式",
        choices=[
            ("private", "仅自己可见"),
            ("unlisted", "通过链接分享"),
            ("public", "公开展示"),
        ],
        validators=[DataRequired()],
    )
    image_ids = SelectMultipleField("选择并排列图片", coerce=int, validators=[Optional()])
    submit = SubmitField("保存相册")


class ApiTokenForm(FlaskForm):
    name = StringField("钥匙名称", validators=[DataRequired(), Length(max=80)])
    scopes = SelectMultipleField(
        "可以做什么",
        choices=[
            ("images:read", "查看自己的图片"),
            ("images:write", "上传和整理图片"),
        ],
        validators=[DataRequired()],
    )
    expires_days = IntegerField(
        "有效天数",
        default=90,
        validators=[DataRequired(), NumberRange(min=1, max=365)],
    )
    submit = SubmitField("创建钥匙")
