from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from peewee import Model

from .datasets import _read_caption_bytes
from .models import CaptionJobCreateRequest, CaptionPrediction
from .store import CaptionStore
from .writer import CaptionWriteConflict, apply_affixes, atomic_write_caption, merge_caption


class CaptionResultWriter:
    """Apply output policy and record results for generation and review commits.

    The worker owns inference and per-item error isolation. This writer owns
    merging the scanned text, staging or writing the result, and updating the
    ledger only after a successful write. File safety remains in writer.py.
    """

    def __init__(
        self,
        store: CaptionStore,
        job_id: str,
        request: CaptionJobCreateRequest,
        source_root: Path,
    ) -> None:
        self.store = store
        self.job_id = job_id
        self.request = request
        self.source_root = source_root

    def skip_existing(self, row: Model) -> bool:
        fingerprint = _fingerprint(row)
        if (
            self.request.output.stageBeforeWrite
            or self.request.output.conflictPolicy != "skip"
            or fingerprint is None
        ):
            return False
        self.store.update_item(
            self.job_id,
            row.id,
            state="skipped",
            finalText=row.existing_text,
            error="已有 Caption，按跳过策略未执行推理。",
        )
        return True

    def save_prediction(self, row: Model, prediction: CaptionPrediction, *, started: float) -> None:
        fingerprint = _fingerprint(row)
        generated = prediction.text.strip()
        if self.request.outputMode != "tags":
            options = self.request.postprocess
            generated = apply_affixes(generated, options.prefix, options.suffix, options.separator)
        if not generated:
            raise RuntimeError("模型返回了空 Caption")

        final_text, should_write = self._merge(
            row, generated, fingerprint, self.request.output.conflictPolicy,
        )
        fields = {
            "generatedText": generated,
            "tags": prediction.tags,
            "raw": prediction.raw if self.request.output.saveRawResult else None,
            "elapsedMs": round((time.perf_counter() - started) * 1000),
        }
        self._persist(
            row, final_text, should_write, fingerprint,
            stage=self.request.output.stageBeforeWrite,
            backup_existing=self.request.output.backupExisting,
            fields=fields,
        )

    def commit_item(self, row: Model, *, policy: str, backup_existing: bool) -> None:
        if row.written or (row.state == "failed" and not row.edited):
            return
        fingerprint = _fingerprint(row)
        if row.edited:
            # Review edits are authoritative, including empty or untrimmed text.
            final_text, should_write = row.final_text, True
        else:
            final_text, should_write = self._merge(row, row.generated_text, fingerprint, policy)
        self._persist(
            row, final_text, should_write, fingerprint,
            stage=False, backup_existing=backup_existing, fields={"error": None},
        )

    def _merge(
        self,
        row: Model,
        generated: str,
        fingerprint: Optional[Dict[str, Any]],
        policy: str,
    ) -> Tuple[str, bool]:
        # An undecodable caption has an empty text snapshot but nonempty bytes.
        # Policies retaining existing content must not mistake that for empty.
        if (
            policy in {"append", "prepend", "fill_empty"}
            and not row.existing_text
            and fingerprint
            and fingerprint.get("size")
        ):
            caption_path = Path(row.caption_path).resolve()
            try:
                caption_path.relative_to(self.source_root.resolve())
            except ValueError as exc:
                raise CaptionWriteConflict("Caption 输出路径已离开获准的数据集目录。") from exc
            content = _read_caption_bytes(caption_path)
            if content is not None:
                try:
                    content.decode("utf-8-sig")
                except UnicodeError as exc:
                    raise CaptionWriteConflict(
                        "现有 Caption 不是有效的 UTF-8，请先手动修复或明确选择覆盖策略。"
                    ) from exc
        return merge_caption(
            row.existing_text,
            generated,
            exists=fingerprint is not None,
            policy=policy,
            separator=self.request.postprocess.separator,
        )

    def _persist(
        self,
        row: Model,
        text: str,
        should_write: bool,
        fingerprint: Optional[Dict[str, Any]],
        *,
        stage: bool,
        backup_existing: bool,
        fields: Dict[str, Any],
    ) -> None:
        fields.update(state="succeeded" if stage or should_write else "skipped", finalText=text)
        if not stage and should_write:
            written_hash = atomic_write_caption(
                job_id=self.job_id,
                caption_path=Path(row.caption_path),
                allowed_root=self.source_root,
                relative_path=row.relative_path,
                text=text,
                expected_fingerprint=fingerprint,
                backup_existing=backup_existing,
            )
            fields.update(written=True, writtenHash=written_hash)
        self.store.update_item(self.job_id, row.id, **fields)


def _fingerprint(row: Model) -> Optional[Dict[str, Any]]:
    if not row.existing_fingerprint:
        return None
    payload = json.loads(row.existing_fingerprint)
    return payload if isinstance(payload, dict) else None
