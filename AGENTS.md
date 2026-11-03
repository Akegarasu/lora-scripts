# Agent 导航

- **使用项目**：[使用指南](docs/agent/usage/README.md)；先发现能力、检查数据、预览配置，再提交任务。
- **开发项目**：[开发指南](docs/agent/dev/README.md)；**人类说明**：[文档索引](docs/README.md)。
- 后端检查：`python -m unittest discover -s mikazuki/tests -t .`；前端检查：在 `frontend` 执行 `corepack pnpm test` 和 `corepack pnpm run build`。
- 复用运行中的后端；同一工作区只运行一个队列服务。模型、数据、训练结果和本地配置不提交。
- `scripts/dev` 是上游快照；修改前核对 `scripts/dev/UPSTREAM.md`，不要把生成文件当作参数事实源。
