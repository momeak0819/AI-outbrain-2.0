# 五层 Payload 协议

五层之间优先传递 typed result；对外返回保留 nested envelope 和 legacy flat fields。

## SourceInput

- `source_type`
- `raw_input`
- `input_kind`
- `url`
- `text`
- `audio_file`
- `metadata`

## SourceDocument

- `status`
- `source_type`
- `title`
- `original_url`
- `media_type`
- `metadata`
- `error_code`
- `error`
- `recoverable`

## AcquisitionResult

- `status`
- `source_type`
- `media_type`
- `media_path`
- `artifacts`
- `artifact_records`
- `metadata`
- `error_code`
- `error`
- `recoverable`

`artifact_records` 使用 `AcquisitionArtifact` 描述：

- `path`
- `kind`: `audio` / `video` / `file`
- `role`: `primary` / `source` / `derived`
- `ownership`: `user_owned` / `acquisition_temp` / `persistent`
- `cleanup_policy`: `never` / `on_processing_complete` / `manual`
- `mime`

## ProcessingResult

- `status`
- `engine`
- `processing_mode`
- `raw_transcript`
- `normalized_text`
- `transcript`
- `transcript_chars`
- `segments`
- `markdown_path`
- `txt_path`
- `artifacts`
- `metadata`
- `warnings`
- `error_code`
- `error`
- `recoverable`

## KnowledgeResult

- `status`
- `review_id`
- `review_status`
- `card_draft_path`
- `suggested_categories`
- `obsidian_paths`
- `fallback`
- `readiness`
- `vault_validation`
- `error_code`
- `error`
- `recoverable`

## DeliveryResult

- `status`
- `mode`
- `message`
- `artifacts`
- `files`
- `review_status`
- `error_code`
- `error`
- `recoverable`

## Canonical Failure

所有失败统一为：

```json
{
  "stage": "processing",
  "error_code": "asr_unavailable",
  "error": "用户可读错误",
  "recoverable": true
}
```

`stage` 只允许：

- `source`
- `acquisition`
- `processing`
- `knowledge`
- `delivery`
