-- 一次性输出全部 kill 命令，用于阻塞进程
SELECT GROUP_CONCAT(CONCAT('KILL ', ID, ';') SEPARATOR '\n') AS batch_kill
FROM information_schema.PROCESSLIST
WHERE STATE = 'Waiting for table metadata lock';