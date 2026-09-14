ALTER TABLE video_external_api_scene_bindings
  ADD COLUMN availability_modes_json TEXT NULL;

UPDATE video_external_api_scene_bindings
SET availability_modes_json = CASE
  WHEN availability_mode = 'text_to_video' THEN '["text_to_video"]'
  WHEN availability_mode = 'image_to_video' THEN '["image_to_video"]'
  ELSE '["text_to_video", "image_to_video"]'
END
WHERE availability_modes_json IS NULL OR availability_modes_json = '';

ALTER TABLE video_tasks
  ADD COLUMN generation_mode VARCHAR(30) NOT NULL DEFAULT '';

UPDATE video_tasks
SET generation_mode = CASE
  WHEN reference_images IS NULL OR reference_images = '' OR reference_images = '[]' THEN 'text_to_video'
  ELSE 'image_to_video'
END
WHERE generation_mode IS NULL OR generation_mode = '';
