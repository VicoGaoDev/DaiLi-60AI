ALTER TABLE external_api_scene_bindings
  ADD COLUMN custom_size_min INT NOT NULL DEFAULT 256 AFTER hide_custom_size,
  ADD COLUMN custom_size_max INT NOT NULL DEFAULT 3840 AFTER custom_size_min,
  ADD COLUMN custom_size_step INT NOT NULL DEFAULT 8 AFTER custom_size_max;
