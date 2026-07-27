# Next Trainer Vue 3 Frontend

这是用于替换旧 VuePress 构建产物的新 Vue 3 前端工程。旧前端已完整保存在仓库根目录的 `frontendbak/`。

## 开发

```powershell
nvm use 22.17.1
npm install
npm run dev
```

开发服务器默认运行于 `http://127.0.0.1:5173`，并将 `/api`、`/proxy` 和 `/font-roboto` 转发至 `http://127.0.0.1:28000`。

## 构建

```powershell
npm run build
```

生产文件输出到 `frontend/dist/`，由现有 FastAPI 应用直接托管。

## 当前状态

当前版本是可运行的重构基线，不是完整功能版本。已实现应用外壳、主题、响应式导航、兼容路由及代理 iframe。训练、Tagger、数据集编辑等业务必须按照 `MIGRATION.md` 逐项迁移并验证后启用。

工程固定使用 Node 22 LTS。Node 25 在当前 Windows 环境执行 esbuild 二进制时不稳定，不作为受支持的开发版本。
