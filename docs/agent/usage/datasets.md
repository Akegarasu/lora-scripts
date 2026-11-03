# 数据、Caption 与标签编辑

训练草稿直接引用目录；Caption/Tag Editor 的 dataset ID 来自扫描快照，二者不能替代训练的 `dataset.root`。

## 检查数据

文件浏览 `GET /api/v2/files?root=train&kind=dataset`；`train` 和 `datasets` 都映射仓库的 `train/`。`workspace` 映射仓库根，`models` 映射 `models/`，`output`/`outputs` 映射 `output/`。路径必须留在所选 root 内，不通过 `..` 或符号链接绕过范围。

一个 simple 数据集的图片必须直接放在 `dataset.root` 目录，使用同名文本 sidecar：`001.png` 对应 `001.txt`。训练 simple 模式只加载这一层图片，不递归加载子目录；不要传入旧式 `N_name` 数据子目录的父目录，重复次数用 `numRepeats` 显式设置。训练 simple 编译器与 Caption 扫描支持 `.jpg/.jpeg/.png/.webp/.bmp`；通用文件浏览还能显示 GIF/AVIF，不表示 Caption 或训练支持这些格式。

扫描 Caption 数据集：

```http
POST /api/v2/caption/datasets/inspect
Content-Type: application/json

{"root":"train","path":"example","recursive":true,"captionExtension":".txt","initialLimit":20}
```

记录 `dataset.id`、`total`、`withCaption`、`withoutCaption`、`truncated`。首批 items 不是全量；用 `GET /caption/datasets/{dataset_id}/items?offset=0&limit=100` 分页。扫描默认最多 10000 张，可设置 `maxImages`，上限 50000。`truncated=true` 时不得宣称已检查全部数据。snapshot ID 在后端重启后需重新获取；外部修改文件后也应重新扫描。

检查图片错误、caption 是否缺失/为空/被截断、尺寸及训练内容是否匹配。API 写入的 caption 后缀仅允许 `.txt`、`.caption`、`.tags`。

## 自动 Caption

1. `GET /api/v2/caption/models`：查实际模型 ID、outputModes、设备、参数、状态与缺失依赖。`downloadable` 可能在首次使用下载权重；不可把 unavailable 当作可运行。
2. 通过扫描获取 datasetId。只处理部分图片时提供 `itemIds`；省略表示快照内全部图片。
3. `POST /api/v2/caption/jobs` 创建任务。以下 JSON 的模型 ID 需替换为目录返回值：

```json
{
  "datasetId": "<inspect 返回的 ID>",
  "modelId": "<models 返回的 ID>",
  "outputMode": "tags",
  "output": {
    "stageBeforeWrite": true,
    "conflictPolicy": "skip",
    "backupExisting": true
  },
  "runtime": {"device": "auto", "batchSize": 1}
}
```

4. 查 `GET /caption/jobs/{job_id}`，用 `/items?offset=0&limit=100` 分页检查 `finalText`。`stageBeforeWrite=true` 在生成后进入 `awaiting_review`，尚未写入 sidecar。
5. 需要修订时 `PATCH /caption/jobs/{job_id}/items/{item_id}`，body 为 `{"finalText":"..."}`；完成检查后 `POST /caption/jobs/{job_id}/commit`，body 可为 `{}` 或带 `itemIds`。

`stageBeforeWrite` 的 API 默认值是 false；需要复核时必须显式设 true。默认冲突策略 `skip` 保留已有文件；`fill_empty` 填空，`overwrite` 覆盖，`prepend`/`append` 合并。只有用户要求的写入范围才应提交，不因生成成功就推断允许覆盖既有标签。

用 `POST /caption/jobs/{job_id}/cancel` 取消，`GET /caption/jobs/{job_id}/logs?tail=200` 看日志。`partial`、`conflicts`、逐图 failed 都需要查看详情；不能只报告已完成总数。服务重启后的活动任务标为 `interrupted`，不会自动重跑。`awaiting_review` 属于生成阶段终态，但仍可提交。

## 人工批量修改

Tag Editor 使用独立扫描和 revision。基址 `/api/v2/tag-editor`：

1. `POST /datasets/inspect`，请求结构同 Caption 扫描，保留 dataset ID 与 revision。
2. `POST /datasets/{dataset_id}/changes/preview`，先生成具体 diff：

```json
{
  "revision": "<inspect 返回的 revision>",
  "scope": {"mode":"include","includeIds":["<item ID>"]},
  "operations": [{"type":"add","values":["example_tag"],"position":"end"}],
  "sampleLimit": 20
}
```

3. 检查 `matched/changed/issues/diffs`；`diffs` 只是样本，不一定是全部变化。可用 `scope.mode=filter` 和 query/state/exclusions 表示筛选集合，但不要默认把操作扩展为全库。
4. `POST /datasets/{dataset_id}/changes/apply`，body 为 `{"changeSetId":"<preview 的 id>","revision":"<同一 revision>","backupExisting":true}`。
5. `GET /changes/{change_set_id}` 和 `/results` 检查最终结果；支持回滚时 `POST /changes/{change_set_id}/rollback`。

支持 set/add/remove/replace/normalize；完整字段由 OpenAPI schema 提供。revision 或文件内容已变化时重新扫描、预览；不要为了通过检查而用旧 diff 覆盖最新文件。回滚也检测内容冲突，不能保证撤销外部修改。变更历史与备份位于 `config/tag-editor-changes/`；不要清理后仍承诺可回滚。
