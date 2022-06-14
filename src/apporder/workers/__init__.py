import logging
import os
import time

from noonutil.v1 import workerutil

from liborder.context import Context
from liborder.domain import boilerplate_event

logger = logging.getLogger(__name__)

workers = workerutil.ThreadedWorkers()

IS_TESTING = os.getenv('TESTING')


# rethink this whole worker thing which will read from events table
#  this will limit parallel processing
def event_processor(action_code, sleep_time=5):
    def action_processor(fn):
        def wrapper():
            while True:
                processed_events = False
                with Context.service():
                    events = boilerplate_event.get_events(action_code)
                for event in events:
                    try:
                        with Context.service():
                            fn(event)
                            boilerplate_event.delete_event(event['id_boilerplate_event'])
                            processed_events = True
                    except Exception as e:
                        if IS_TESTING:
                            raise e
                        else:
                            # todo: change to error later
                            logger.warning(f"Failed to process event {event} - error: {e} {e.__traceback__}")
                # For testing we want to process all events without sleeping
                if IS_TESTING:
                    # there could be more events, so loop again
                    if processed_events:
                        continue
                    break
                time.sleep(sleep_time)

        return wrapper

    return action_processor
