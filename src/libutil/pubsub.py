import os

from google.cloud import pubsub
from google.cloud import pubsub_v1
from noonutil.v1 import miscutil

ENV = os.environ['ENV']


def pub(topic, message, project=None):
    client = get_pub_client()
    return client.publish(get_topic_key(topic, project), str_to_bytes(message))


def get_publisher(topic, project=None):
    client = get_pub_client()
    topic = get_topic_key(topic, project)
    return lambda msg: client.publish(topic, str_to_bytes(msg)).result()


MB = 1024 * 1024
DEFAULT_FLOW = pubsub.types.FlowControl(max_bytes=20 * MB, max_messages=10)


def sub(subscription, callback, project=None):
    client = get_sub_client()
    return client.subscribe(get_subscription_key(subscription, project), callback=callback, flow_control=DEFAULT_FLOW)


def subpull(subscription, project=None, max_pull_messages=10):
    client = get_sub_v1_client()
    return client.pull(
        subscription=get_subscription_key(subscription, project),
        max_messages=max_pull_messages,
        return_immediately=True
    )


def acknowlegde(subscription, ids, project=None):
    client = get_sub_v1_client()
    client.acknowledge(
        subscription=get_subscription_key(subscription, project),
        ack_ids=ids
    )


def get_pub_client():
    return pubsub.PublisherClient()


def get_sub_client():
    return pubsub.SubscriberClient()


def get_sub_v1_client():
    return pubsub_v1.SubscriberClient()


@miscutil.cached()
def get_project():
    if 'GOOGLE_CLOUD_PROJECT' in os.environ:
        return os.environ['GOOGLE_CLOUD_PROJECT']
    return 'noon-staging' if ENV in ('dev', 'staging') else 'noon-production'


def get_topic_key(name, project=None):
    if name.startswith('projects/'):
        return name
    return 'projects/{project}/topics/{name}'.format(project=project or get_project(), name=name)


def get_subscription_key(name, project=None):
    if name.startswith('projects/'):
        return name
    return 'projects/{project}/subscriptions/{name}'.format(project=project or get_project(), name=name)


def str_to_bytes(msg):
    return msg.encode('utf8') if isinstance(msg, str) else msg


if ENV == 'dev':
    pub = lambda *args, **kwargs: None
