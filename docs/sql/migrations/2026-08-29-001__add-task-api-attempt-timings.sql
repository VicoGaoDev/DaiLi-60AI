ALTER TABLE task_api_attempts ADD COLUMN external_http_ms INTEGER NULL;
ALTER TABLE task_api_attempts ADD COLUMN result_download_ms INTEGER NULL;
ALTER TABLE task_api_attempts ADD COLUMN cos_upload_ms INTEGER NULL;
ALTER TABLE task_api_attempts ADD COLUMN response_preview TEXT;
