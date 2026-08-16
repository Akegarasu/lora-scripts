from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from pydantic import ValidationError

from .models import SimpleDatasetDraft, ValidationMessage

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}


def normalize_resolution(value: Any) -> List[int]:
    if isinstance(value, int):
        return [value, value]
    if isinstance(value, str) and value.isdigit():
        size = int(value)
        return [size, size]
    if isinstance(value, list) and len(value) == 2:
        return [int(value[0]), int(value[1])]
    if isinstance(value, tuple) and len(value) == 2:
        return [int(value[0]), int(value[1])]
    raise ValueError("resolution must be an integer or [width, height]")


def build_simple_dataset(
    raw_dataset: Dict[str, Any],
    *,
    validate_paths: bool = True,
    base_dir: Optional[Path] = None,
) -> Tuple[Dict[str, Any], List[ValidationMessage]]:
    try:
        dataset = SimpleDatasetDraft(**(raw_dataset or {}))
    except ValidationError as exc:
        first_error = exc.errors()[0] if exc.errors() else {}
        location = ".".join(str(item) for item in first_error.get("loc", ()))
        field = f"dataset.{location}" if location else "dataset"
        return {}, [
            ValidationMessage(
                severity="error",
                code="dataset.invalid",
                field=field,
                message=f"数据集参数无效：{first_error.get('msg') or str(exc)}",
            )
        ]
    errors: List[ValidationMessage] = []
    root = _resolve_path(dataset.root, base_dir)

    if root is None:
        errors.append(
            ValidationMessage(
                severity="error",
                code="dataset.root.required",
                field="dataset.root",
                message="数据集目录不能为空。",
            )
        )
    elif validate_paths:
        if validate_paths and not root.exists():
            errors.append(
                ValidationMessage(
                    severity="error",
                    code="dataset.root.missing",
                    field="dataset.root",
                    message=f"数据集目录不存在：{_display_path(root)}",
                )
            )
        elif not root.is_dir():
            errors.append(
                ValidationMessage(
                    severity="error",
                    code="dataset.root.not_folder",
                    field="dataset.root",
                    message=f"数据集路径必须是目录：{_display_path(root)}",
                )
            )
        elif not any(p.suffix.lower() in IMAGE_EXTENSIONS for p in root.rglob("*") if p.is_file()):
            errors.append(
                ValidationMessage(
                    severity="error",
                    code="dataset.images.empty",
                    field="dataset.root",
                    message=f"数据集目录中没有支持的图片文件：{_display_path(root)}",
                )
            )

    try:
        resolution = normalize_resolution(dataset.resolution)
        if resolution[0] <= 0 or resolution[1] <= 0:
            raise ValueError
    except Exception:
        resolution = [1024, 1024]
        errors.append(
            ValidationMessage(
                severity="error",
                code="dataset.resolution.invalid",
                field="dataset.resolution",
                message="分辨率必须是正整数或 [宽, 高]。",
            )
        )

    if dataset.batchSize <= 0:
        errors.append(
            ValidationMessage(
                severity="error",
                code="dataset.batch_size.invalid",
                field="dataset.batchSize",
                message="数据集 Batch Size 必须大于 0。",
            )
        )

    if dataset.numRepeats <= 0:
        errors.append(
            ValidationMessage(
                severity="error",
                code="dataset.num_repeats.invalid",
                field="dataset.numRepeats",
                message="数据重复次数必须大于 0。",
            )
        )

    if dataset.enableBucket and dataset.bucketResoSteps <= 0:
        errors.append(
            ValidationMessage(
                severity="error",
                code="dataset.bucket_step.invalid",
                field="dataset.bucketResoSteps",
                message="bucket 步长必须大于 0。",
            )
        )
    elif dataset.enableBucket and (
        dataset.minBucketReso <= 0
        or dataset.maxBucketReso < dataset.minBucketReso
        or dataset.minBucketReso % dataset.bucketResoSteps != 0
        or dataset.maxBucketReso % dataset.bucketResoSteps != 0
    ):
        errors.append(
            ValidationMessage(
                severity="error",
                code="dataset.bucket_step.unaligned",
                field="dataset.bucketResoSteps",
                message="Bucket 最小/最大分辨率必须有效，且能被 bucket 步长整除。",
            )
        )

    caption_extension = dataset.captionExtension.strip()
    if caption_extension and not caption_extension.startswith("."):
        caption_extension = f".{caption_extension}"

    config = {
        "general": {
            "shuffle_caption": dataset.shuffleCaption,
            "caption_extension": caption_extension or ".txt",
            "keep_tokens": dataset.keepTokens,
        },
        "datasets": [
            {
                "resolution": resolution,
                "batch_size": dataset.batchSize,
                "enable_bucket": dataset.enableBucket,
                "min_bucket_reso": dataset.minBucketReso,
                "max_bucket_reso": dataset.maxBucketReso,
                "bucket_reso_steps": dataset.bucketResoSteps,
                "bucket_no_upscale": dataset.bucketNoUpscale,
                "subsets": [
                    {
                        "image_dir": _display_path(root) if root is not None else "",
                        "num_repeats": dataset.numRepeats,
                    }
                ],
            }
        ],
    }
    return config, errors


def _resolve_path(value: Optional[str], base_dir: Optional[Path]) -> Optional[Path]:
    if value is None or not value.strip():
        return None
    path = Path(value).expanduser()
    if not path.is_absolute() and base_dir is not None:
        path = base_dir / path
    return path.resolve()


def _display_path(path: Path) -> str:
    return str(path.resolve()).replace("\\", "/")
