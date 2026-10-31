# The queue is a directory with one file per op

The spec used a single `queue.jsonl` that the service renames before it reads. That races: Node's append is open → write → close, so a write to an fd that was opened before the rename lands in an inode the service has already read and deleted. Node has no built-in `flock`. So the extension writes each op to a temp file and renames it into `queue/` (`<ms>-<8 hex>.json`). The service applies the files in name order and deletes each one only after a successful sync.
