# 训练与队列

HTTP 基址为 `/api/v2`；MCP 对应操作见 [MCP 使用](mcp.md)。

## 发现训练能力

- `GET /trainers`：当前训练器 ID、状态及 `manifestHash`。
- `GET /trainers/{id}`：完整定义、模型资产字段、数据集默认值。
- `GET /trainers/{id}/params?view=recommended`：常用参数；`advanced`、`all` 查看更多。
- `GET /training/schema`：TrainDraft 与 simple 数据集的完整标准 JSON Schema。
- `GET /devices/gpus`：设备信息。
- `GET /files?root=models&kind=model`：模型目录；文件列表不递归，按目录逐层浏览。

当前目录覆盖 `sd.lora`、`sdxl.lora`、`sd3.lora`、`flux.lora`、`chroma.lora`、`lumina.lora`、`hunyuan_image.lora`、`anima.lora`、`moss_image.lora`。以在线返回为准，实验性状态不能视为完整验证。

参数 `priority` 只决定展示层级；`effectiveDefault` 才是工作台默认值。不要将 `recommended` 解读为该参数应自动开启，也不要照搬其他模型的训练配方。

## 草稿与编译

下面是结构示例，路径需换成已确认存在的文件；学习率、时长等应由本次训练目标确定：

```json
{
  "trainerId": "sdxl.lora",
  "name": "example-sdxl",
  "modelAssets": {
    "pretrained_model_name_or_path": "models/sdxl-base.safetensors"
  },
  "dataset": {
    "mode": "simple",
    "root": "train/example",
    "captionExtension": ".txt",
    "resolution": [1024, 1024],
    "batchSize": 1,
    "numRepeats": 1
  },
  "params": {
    "output_dir": "output",
    "max_train_steps": 100,
    "network_train_unet_only": true
  },
  "runtime": {"gpuIds": ["0"], "numCpuThreadsPerProcess": 8},
  "sample": {"enabled": false}
}
```

将草稿直接作为 `POST /compile?persist=false&validate_paths=true` 的 JSON body。返回 `errors`、`warnings`、生成的 TOML 和命令；只预览不会启动训练。`persist=true` 会将有效配置写入新的 run 目录；`validate_paths=false` 只适合离线配置检查，不能证明数据或权重可用。

`name` 同时作为输出模型名，不能包含路径分隔符。数据集、输出名称、采样配置由结构化字段管理；不要在 `params` 再填 `dataset_config`、`train_data_dir`、`train_batch_size`、`output_name`、`sample_prompts` 等被接管字段。当前 API 数据集只支持 `mode=simple`；复杂多子集 TOML 需走上游脚本入口。

常见冲突：

- 显式 `max_train_epochs` 与 `max_train_steps` 二选一；仅显式提供 steps 时编译器会移除继承的 epochs 默认值。
- latent 缓存与 `color_aug`、`random_crop` 冲突。
- 文本缓存与 shuffle、tag dropout、token warmup 冲突；文本编码器是否可训练取决于训练器。SDXL、Anima、MOSS-Image 缓存文本输出时必须仅训练 U-Net/DiT。
- 数据集 bucket 步长需满足模型对齐；沿用所选训练器的 `datasetDefaults`。
- 恢复 optimizer/state 的 `resume` 与仅加载 `network_weights` 含义不同；查看所选训练器参数说明，不把加载权重说成完整恢复。

启用 `sample` 时必须给出 prompts 和一个采样周期（`everyNEpochs` 或 `everyNSteps`），或使用训练器支持的 `sample_at_first`。

## 提交、查询与停止

`POST /jobs?validate_paths=true` 接收同一份草稿，重新编译并执行运行时检查，成功返回 `job` 和 `compile`。此操作会立即入队，空闲时直接启动；没有“只创建但不执行”的任务模式。编译错误返回 HTTP 400，不产生训练任务；即使运行时检查失败，也可能已有编译产物。

| 操作 | 接口 |
| --- | --- |
| 最近任务（新到旧，最多 200） | `GET /jobs?limit=50` |
| 任务状态 | `GET /jobs/{job_id}` |
| 原草稿和实际配置 | `GET /jobs/{job_id}/artifacts` |
| 日志尾部（最多 5000 行） | `GET /jobs/{job_id}/logs?tail=200` |
| 指标快照/增量 | `GET /jobs/{job_id}/metrics?cursor=0&max_points=2000` |
| 终止指定任务 | `POST /jobs/{job_id}/terminate` |

训练状态通常为 `queued → running → succeeded/failed`；终止为 `terminating → terminated`。对等待中的任务请求终止后，它可能要等执行槽释放才落到终态；不会因此启动训练。已终止任务再次 terminate 返回当前记录。

训练和 Caption 共用进程内的一个 GPU 槽位，默认同时只运行一个任务，CPU Caption 也走此槽位。当前实现不承诺严格 FIFO、优先级、暂停、重排或自动重试；列表排序不等于实际调度顺序。不要开多 worker 或第二个后端访问同一工作区。服务重启将未终结训练标为 failed，不自动恢复或接管旧进程。

创建请求超时可能已经入队：先查询最近任务，对比名称、时间和配置，再决定是否重试。需要重试时根据原 draft 新建任务；需要接续训练时另外确认可用 state 和 `resume` 设置。

迭代旧任务时，从 artifacts 响应读取 `draft`、实际 `trainConfig`、`datasetConfig` 和可选 `samplePrompts`。在复制的草稿上调整参数和新的 `name`，再次编译；保留原记录作为比较基线。不要直接改写已运行任务的产物。

## 产物

- `config/runs/<run_id>/`：`draft.json`、`train.toml`、`dataset.toml`、`command.json`、`job.json`，以及可选 `sample_prompts.txt`。
- `logs/jobs/<job_id>.log`：进程输出。
- `job.artifacts.loggingDir`：该任务 TensorBoard 事件目录；API 直接解析，无需启动 TensorBoard 服务。
- 模型与样图写到编译后 `output_dir`，默认工作台输出根为 `output/`；`config/runs` 本身不是模型目录。

只有服务端任务终态和输出文件共同确认后，才报告完成。质量判断需另看样图或用户的验证方法。
