# sd-scripts 上游快照

本目录同步自 [kohya-ss/sd-scripts v0.12.0](https://github.com/kohya-ss/sd-scripts/commit/690ea7f96c23182352ec63def76d431c6120bd2f)，
提交时间为 2026-09-24 10:34:44 UTC，2026-09-28 核对时为 `main` 最新提交。
可供工具读取的来源信息保存在 `UPSTREAM.json`，参数清单生成器会将其写入 manifest。

## 同步基线与范围

- 原有 223 个受 Git 跟踪的文件，规范化 CRLF 后全部与官方 v0.11.0
  `b8d1eb067eba32bb105984678b97f05b11452940` 一致，没有本地代码补丁。
- 本轮上游文件新增 16 个、修改 65 个、删除 1 个；另增加本说明与 `UPSTREAM.json`。
- 沿用现有 vendoring 范围，排除上游 `.ai/`、`.github/`、`tests/`，不收录 Python 字节码。
- `pytorch_lightning` 兼容包及 `library` 拆分模块均为上游实现，已保留；没有覆盖项目自定义补丁。
- `gen_img_diffusers.py` 随上游删除；训练入口及 `scripts/stable` 不受此删除影响。

## 依赖与验证边界

本目录 `requirements.txt` 原样保留上游推荐版本。v0.12.0 的
[发布说明](./README.md#change-history) 同时说明旧版依赖仍可使用；本项目实际安装由根目录依赖文件控制，
同步源码不表示已升级当前环境。

| 依赖 | 旧上游推荐 | v0.12.0 推荐 |
| --- | --- | --- |
| accelerate | 1.6.0 | 1.15.0 |
| transformers | 4.54.1 | 5.17.0 |
| diffusers | 0.32.1 | 0.40.0 |
| huggingface-hub | 0.34.3 | 1.32.0 |
| safetensors | 0.4.5 | 0.8.0 |
| schedulefree | 1.4 | 1.4.1 |

上游新增 Windows ARM64 的 OpenCV/TensorBoard 条件依赖及 OpenCV 回退实现。
同步时在项目现有 Python 3.10、PyTorch 2.4.1+cu121、transformers 4.54.1 环境中，
实际导入全部 8 个工作台训练器并调用 `setup_parser()`，成功生成参数清单，未安装新依赖。
这验证了导入与参数定义，不代表所有模型、量化或编译路径已经完成训练验证；没有加载模型或运行 GPU 训练。

重新生成参数清单：

```powershell
.\venv\Scripts\python.exe -m mikazuki.catalog.inspector generate --scripts-root scripts/dev
```

后续同步应先验证本地与 `UPSTREAM.json` 所指快照的差异，再更新来源记录和 manifest，
避免把本地适配误当作上游文件覆盖。
