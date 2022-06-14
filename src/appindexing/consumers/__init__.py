from eventpubsub import EventSubscriber
from noonutil.v1 import workerutil

# workers for `one` worker
workers = workerutil.ThreadedWorkers()

# workers for `consume` worker
consume_workers = workerutil.ThreadedWorkers()
subscriber = EventSubscriber('', consume_workers)
