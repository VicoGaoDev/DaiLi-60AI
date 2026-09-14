ALTER TABLE external_api_configs
  ADD COLUMN call_mode VARCHAR(20) NOT NULL DEFAULT 'sync',
  ADD COLUMN submit_success_statuses_json TEXT NULL,
  ADD COLUMN poll_url VARCHAR(500) NOT NULL DEFAULT '',
  ADD COLUMN poll_method VARCHAR(10) NOT NULL DEFAULT 'GET',
  ADD COLUMN poll_headers_json TEXT NULL,
  ADD COLUMN poll_payload_json TEXT NULL,
  ADD COLUMN task_id_field VARCHAR(255) NOT NULL DEFAULT '',
  ADD COLUMN result_status_field VARCHAR(255) NOT NULL DEFAULT '',
  ADD COLUMN result_success_values_json TEXT NULL,
  ADD COLUMN result_failed_values_json TEXT NULL,
  ADD COLUMN result_error_field VARCHAR(255) NOT NULL DEFAULT '',
  ADD COLUMN poll_result_base64_field VARCHAR(255) NOT NULL DEFAULT '',
  ADD COLUMN poll_result_url_field VARCHAR(255) NOT NULL DEFAULT '',
  ADD COLUMN poll_interval_seconds INT NOT NULL DEFAULT 5,
  ADD COLUMN poll_timeout_seconds INT NOT NULL DEFAULT 600;

UPDATE external_api_configs
SET call_mode = 'sync'
WHERE call_mode IS NULL OR call_mode = '';

UPDATE external_api_configs
SET submit_success_statuses_json = '[200, 201, 202]'
WHERE submit_success_statuses_json IS NULL OR submit_success_statuses_json = '';

UPDATE external_api_configs
SET poll_headers_json = '{}'
WHERE poll_headers_json IS NULL OR poll_headers_json = '';

UPDATE external_api_configs
SET poll_payload_json = '{}'
WHERE poll_payload_json IS NULL;

UPDATE external_api_configs
SET result_success_values_json = '["success", "succeeded", "completed"]'
WHERE result_success_values_json IS NULL OR result_success_values_json = '';

UPDATE external_api_configs
SET result_failed_values_json = '["failed", "error", "cancelled"]'
WHERE result_failed_values_json IS NULL OR result_failed_values_json = '';

ALTER TABLE tasks
  ADD COLUMN provider_api_config_id BIGINT NULL,
  ADD COLUMN provider_task_id VARCHAR(255) NOT NULL DEFAULT '',
  ADD COLUMN provider_status VARCHAR(50) NOT NULL DEFAULT '',
  ADD COLUMN provider_error_message TEXT NULL,
  ADD COLUMN provider_response_preview TEXT NULL,
  ADD COLUMN poll_count INT NOT NULL DEFAULT 0,
  ADD COLUMN last_polled_at DATETIME NULL,
  ADD COLUMN next_poll_at DATETIME NULL;
