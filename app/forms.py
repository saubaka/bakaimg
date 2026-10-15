"""Forms for identity, administration and image management."""

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


class StyledForm(FlaskForm):
    """Gives rendered controls the design-system classes; markup stays in the templates."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self:
            if isinstance(field, SubmitField):
                css_class = "ba-button"
            elif isinstance(field, (StringField, IntegerField)):
                css_class = "ba-input"
            else:
                continue
            render = dict(field.render_kw or {})
            render.setdefault("class", css_class)
            field.render_kw = render


class GatewayConnectionForm(StyledForm):
    issuer = StringField("服务地址", validators=[DataRequired(), Length(max=500)])
    client_id = StringField("应用编号", validators=[DataRequired(), Length(max=200)])
    client_secret = PasswordField(
        "应用密钥",
        validators=[Optional(), Length(min=8, max=512)],
    )
    submit = SubmitField("保存并验证连接")


class LocalAdminSetupForm(StyledForm):
    username = StringField("管理员用户名", validators=[DataRequired(), Length(min=3, max=50)])
    email = StringField("管理员邮箱", validators=[DataRequired(), Length(max=254)])
    display_name = StringField("显示名称", validators=[DataRequired(), Length(min=1, max=80)])
    password = PasswordField("管理员密码", validators=[DataRequired(), Length(min=12, max=256)])
    confirm_password = PasswordField(
        "确认管理员密码",
        validators=[DataRequired(), EqualTo("password", message="两次输入的密码不一致。")],
    )
    submit = SubmitField("创建首位超级管理员")


class LocalLoginForm(StyledForm):
    identity = StringField(
        "用户名或邮箱",
        validators=[
            DataRequired(message="请填写用户名或邮箱。"),
            Length(max=254, message="请控制在254个字符以内。"),
        ],
    )
    password = PasswordField(
        "密码",
        validators=[
            DataRequired(message="请填写密码。"),
            Length(max=256, message="密码不能超过256个字符。"),
        ],
    )
    remember = BooleanField("记住我")
    submit = SubmitField("登录")


class LocalRegisterForm(StyledForm):
    username = StringField(
        "用户名",
        validators=[
            DataRequired(message="请填写用户名。"),
            Length(min=3, max=50, message="用户名需要3～50个字符。"),
        ],
    )
    display_name = StringField(
        "显示名称",
        validators=[
            DataRequired(message="请填写名称。"),
            Length(min=1, max=80, message="名称请控制在80个字符以内。"),
        ],
    )
    email = StringField(
        "邮箱",
        validators=[
            DataRequired(message="请填写邮箱。"),
            Length(max=254, message="邮箱不能超过254个字符。"),
        ],
    )
    password = PasswordField(
        "密码",
        validators=[
            DataRequired(message="请填写密码。"),
            Length(min=12, max=256, message="密码需要12～256个字符。"),
        ],
    )
    confirm_password = PasswordField(
        "确认密码",
        validators=[
            DataRequired(message="请再次输入密码。"),
            EqualTo("password", message="两次输入的密码不一致。"),
        ],
    )
    submit = SubmitField("创建账号")


class UserAdminForm(StyledForm):
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


class RoleForm(StyledForm):
    name = StringField("角色名称", validators=[DataRequired(), Length(max=80)])
    description = StringField("说明", validators=[Optional(), Length(max=255)])
    permission_ids = SelectMultipleField("权限", coerce=int, validators=[Optional()])
    submit = SubmitField("保存角色")


class MaintenanceForm(StyledForm):
    enabled = BooleanField("开启维护模式")
    message = StringField(
        "访客提示",
        validators=[DataRequired(), Length(min=1, max=160)],
    )
    submit = SubmitField("保存维护状态")


class EmptyForm(StyledForm):
    submit = SubmitField("确认")


class TransitionSettingsForm(StyledForm):
    transition_style = RadioField("页面过渡方式", validators=[DataRequired()])
    transition_duration = IntegerField(
        "动画时间（毫秒）", validators=[DataRequired(), NumberRange(min=300, max=2400)]
    )
    transition_color_start = StringField("覆盖起始色", validators=HEX_COLOR_VALIDATORS)
    transition_color_middle = StringField("覆盖过渡色", validators=HEX_COLOR_VALIDATORS)
    transition_color_end = StringField("覆盖结束色", validators=HEX_COLOR_VALIDATORS)
    submit = SubmitField("保存动效设置")


class DialogAppearanceForm(StyledForm):
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


class ImageUploadForm(StyledForm):
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


class ImageEditForm(StyledForm):
    title = StringField(
        "图片标题", validators=[Optional(), Length(max=160, message="标题请控制在160个字符以内。")]
    )
    alt_text = TextAreaField(
        "图片说明", validators=[Optional(), Length(max=240, message="说明请控制在240个字符以内。")]
    )
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


class AlbumForm(StyledForm):
    title = StringField(
        "相册名称",
        validators=[
            DataRequired(message="请填写相册名称。"),
            Length(max=120, message="名称请控制在120个字符以内。"),
        ],
    )
    description = TextAreaField(
        "相册介绍", validators=[Optional(), Length(max=500, message="介绍请控制在500个字符以内。")]
    )
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


class ApiTokenForm(StyledForm):
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
