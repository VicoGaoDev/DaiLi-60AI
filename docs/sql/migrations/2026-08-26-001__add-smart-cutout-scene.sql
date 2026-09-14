ALTER TABLE external_api_configs ADD COLUMN supports_smart_cutout BOOLEAN DEFAULT 0;
ALTER TABLE external_api_configs ADD COLUMN is_active_smart_cutout BOOLEAN DEFAULT 0;
