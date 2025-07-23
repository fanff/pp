# for later use. both in client and server.

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import SERVICE_NAME, Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import (
    BatchSpanProcessor,
    ConsoleSpanExporter,
    SimpleSpanProcessor,
)


def global_tracing_setup(endpoint):
    # create a TracerProvider
    tp = TracerProvider(resource=Resource.create({SERVICE_NAME: "ppapi"}))
    # create a JaegerExporter
    jaeger_exporter = OTLPSpanExporter(endpoint=endpoint)

    # Create a BatchSpanProcessor and add the exporter to it
    span_processor = BatchSpanProcessor(jaeger_exporter)

    # add to the tracer
    tp.add_span_processor(span_processor)
    trace.set_tracer_provider(tp)

    


def local_tracing_setup(service_name="ppapi", exporter="console"):
    # create a TracerProvider
    tp = TracerProvider(resource=Resource.create({SERVICE_NAME: service_name}))

    # create a JaegerExporter
    if exporter == "jaeger":
        exporter = OTLPSpanExporter(endpoint="http://localhost:4318/v1/traces")
        # Create a BatchSpanProcessor and add the exporter to it
        span_processor = BatchSpanProcessor(exporter)
    else:

        def quick_fromatting(span):
            attr_strs = [f"  {k} {v}" for k, v in span.attributes.items()]
            attr_str = "\n".join(attr_strs)

            dur = span.end_time - span.start_time
            return f"{span.name} ({dur/100000000.0} secs)\n{attr_str}\n"

        exporter = ConsoleSpanExporter(formatter=quick_fromatting)
        span_processor = SimpleSpanProcessor(exporter)

    # add to the tracer
    tp.add_span_processor(span_processor)
    tp.get_tracer(__name__)
    return tp
