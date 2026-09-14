ALTER TABLE canvas_nodes
  ADD COLUMN video_task_id INT NULL AFTER task_id;

CREATE INDEX idx_canvas_nodes_video_task_id ON canvas_nodes (video_task_id);

ALTER TABLE canvas_nodes
  ADD CONSTRAINT fk_canvas_nodes_video_task
  FOREIGN KEY (video_task_id) REFERENCES video_tasks(id)
  ON DELETE CASCADE;
