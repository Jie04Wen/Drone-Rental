from __future__ import annotations

import base64
from io import BytesIO

from PIL import Image, ImageOps, UnidentifiedImageError

SUPPORTED_FORMATS = {
    "JPEG": "image/jpeg",
    "PNG": "image/png",
    "GIF": "image/gif",
    "WEBP": "image/webp",
}


# 图片验证和预处理
def prepare_image(content: bytes, max_bytes: int) -> tuple[bytes, str]:
    # 验证、纠正方向、缩放并清除图片元数据
    if not content:
        raise ValueError("图片内容为空！")
    if len(content) > max_bytes:
        raise ValueError("图片不能超过10MB！")

    try:
        with Image.open(BytesIO(content)) as source:
            # 校验图片文件头完整性
            source.verify()

        with Image.open(BytesIO(content)) as source:
            image_format = source.format
            if image_format not in SUPPORTED_FORMATS:
                raise ValueError("目前仅支持JPEG、PNG、GIF和WebP图片")

            # 修复手机照片旋转问题
            image = ImageOps.exif_transpose(source)
            image.thumbnail((2048, 2048))

            if image.mode not in ("RGB", "L"):
                image = image.convert("RGB")

            output = BytesIO()
            image.save(
                output,
                format="JPEG",
                quality=90,
                optimize=True,
            )
            normalized = output.getvalue()
    except (UnidentifiedImageError, OSError) as exc:
        raise ValueError("上传文件不是有效图片！") from exc

    if len(normalized) > max_bytes:
        raise ValueError("图片超过大小限制！")

    return normalized, "image/jpeg"


def to_data_url(content: bytes, mime_type: str) -> str:
    encoded = base64.b64encode(content).decode("ascii")
    return f"data:{mime_type};base64,{encoded}"
