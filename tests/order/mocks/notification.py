from liborder.domain.boilerplate_event import ActionCode
from liborder.domain.notification import notification_order_update
from libexternal.notification import NotificationList


def process_notification_events(skip=False):
    """
    :param skip: if true, we basically clear the db of all notification events
    """

    from apporder.workers.order import event_processor

    def empty(event): pass

    fn = empty if skip else notification_order_update
    event_processor(action_code=ActionCode.NOTIFICATION_ORDER_UPDATE)(fn)()


class NotificationMock:

    calls = []

    # empty db of all notification requests
    def __init__(self):
        process_notification_events(skip=True)
        self.calls = []

    @staticmethod
    def send_mock(notification_mock):
        return lambda notification_req: notification_mock.send(notification_req)

    def send(self, request: NotificationList):
        self.calls.append(request.notifications)

    def get_last_call_template(self):
        lst = self.get_last_call()
        return [f'boilerplate_{el.channel_code}_{el.template_name}' for el in lst]

    def get_last_call(self):
        process_notification_events()
        if len(self.calls) == 0:
            return []
        return self.calls[-1]

    def no_of_calls(self):
        return len(self.calls)


