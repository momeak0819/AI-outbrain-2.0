# Delivery 协议

Delivery 层负责统一输出，不执行业务副作用。

## Canonical Envelope

对外结果包含：

- `source`
- `acquisition`
- `processing`
- `knowledge`
- `delivery`
- `next`

nested envelope 是事实源；flat 字段只是兼容投影。

## Legacy Projection

旧字段继续保留，例如：

- `success`
- `stage`
- `error_code`
- `error`
- `recoverable`
- `transcript`
- `md_path`
- `txt_path`
- `exported_paths`
- `workflow_complete`
- `next_action`
- `next_skill`

## 失败归因

Delivery 优先使用上游明确的 `stage/error_code/error/recoverable`。

只有旧 payload 没有明确 stage 时，才使用 legacy 文案兜底推断。

## Batch

Batch 顶层只聚合：

- `total`
- `succeeded`
- `failed`
- `workflow_complete`
- `items`

每个 item 仍保持单条 canonical envelope。
