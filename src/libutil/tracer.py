import os

from opentelemetry.exporter.cloud_trace import CloudTraceSpanExporter
from opentelemetry.sdk.resources import Resource, SERVICE_NAME
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

ENV = os.getenv('ENV')
GCP_PROJECT_NAME = os.getenv('GCP_PROJECT_NAME')
APPNAME = os.getenv('APPNAME')

tracer_provider = None

if ENV != 'dev':
    # emit to google cloud trace
    exporter = CloudTraceSpanExporter(project_id=GCP_PROJECT_NAME)
    processor = BatchSpanProcessor(exporter)
    if not os.getenv('TESTING'):
        resource = Resource.create({SERVICE_NAME: APPNAME})
        tracer_provider = TracerProvider(resource=resource)
        tracer_provider.add_span_processor(processor)
