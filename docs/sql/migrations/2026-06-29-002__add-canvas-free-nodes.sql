-- Add free-form canvas nodes for text and uploaded images.
-- Task nodes keep node_type='task'; free nodes use task_id=NULL.

ALTER TABLE canvas_nodes
  MODIFY task_id INTEGER NULL;

ALTER TABLE canvas_nodes
  ADD COLUMN node_type VARCHAR(20) NOT NULL DEFAULT 'task';

ALTER TABLE canvas_nodes
  ADD COLUMN content VARCHAR(5000) NOT NULL DEFAULT '';

ALTER TABLE canvas_nodes
  ADD COLUMN image_url VARCHAR(1000) NOT NULL DEFAULT '';
