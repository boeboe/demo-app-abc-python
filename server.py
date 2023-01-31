#!/usr/bin/env python3

import argparse
import json
# import logging
import socket
import sys
import time
from random import randint

import requests
import yaml
from flask import Flask, request
from opentelemetry import trace
from opentelemetry.exporter.zipkin.encoder import Protocol
from opentelemetry.exporter.zipkin.json import ZipkinExporter
from opentelemetry.instrumentation.flask import FlaskInstrumentor
# from opentelemetry.instrumentation.logging import LoggingInstrumentor
from opentelemetry.instrumentation.requests import RequestsInstrumentor
from opentelemetry.instrumentation.wsgi import collect_request_attributes
from opentelemetry.propagate import extract, set_global_textmap
from opentelemetry.propagators.b3 import B3MultiFormat
from opentelemetry.sdk.resources import SERVICE_NAME, Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

app = Flask(__name__)
# logger = logging.getLogger(__name__)

parser = argparse.ArgumentParser()
parser.add_argument('--configfile', type=str, required=True)
args = parser.parse_args()
with open(args.configfile, "r") as stream:
  try:
    pconf = yaml.safe_load(stream)
  except yaml.YAMLError as exc:
    print(exc)

# Check for mandatory config file settings
if "server" not in pconf: sys.exit("Missing server in {}\n{}".format(args.configfile, json.dumps(pconf, sort_keys=True, indent=2)))
if "name" not in pconf["server"]: sys.exit("Missing server.name in {}\n{}".format(args.configfile, json.dumps(pconf, sort_keys=True, indent=2)))
if "port" not in pconf["server"]: sys.exit("Missing server.port in {}\n{}".format(args.configfile, json.dumps(pconf, sort_keys=True, indent=2)))
if "traffic" not in pconf: sys.exit("Missing traffic in {}\n{}".format(args.configfile, json.dumps(pconf, sort_keys=True, indent=2)))
if "upstream_host" not in pconf["traffic"]: sys.exit("Missing traffic.upstream_host in {}\n{}".format(args.configfile, json.dumps(pconf, sort_keys=True, indent=2)))
if "tracing" not in pconf: sys.exit("Missing tracing in {}\n{}".format(args.configfile, json.dumps(pconf, sort_keys=True, indent=2)))
if "endpoint" not in pconf["tracing"]: sys.exit("Missing tracing.endpoint in {}\n{}".format(args.configfile, json.dumps(pconf, sort_keys=True, indent=2)))

# Debug enabled
if "debug" not in pconf["server"]:
  debug = False
else:
  debug = bool(pconf["server"]["debug"])

# Configure zipkin
set_global_textmap(B3MultiFormat())
resource = Resource(attributes={SERVICE_NAME: str(pconf["server"]["name"])})
trace.set_tracer_provider(TracerProvider(resource=resource))

# Create a ZipkinExporter
zipkin_exporter = ZipkinExporter(
    version=Protocol.V2,
    endpoint=str(pconf["tracing"]["endpoint"])
)

# Create a BatchSpanProcessor and add the exporter to it
span_processor = BatchSpanProcessor(zipkin_exporter)

# Add BatchSpanProcessor to the tracer
trace.get_tracer_provider().add_span_processor(span_processor)

# Print OpenTracing payloads to stdout
if debug:
  from opentelemetry.sdk.trace.export import ConsoleSpanExporter
  trace.get_tracer_provider().add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))

# Instrument the request (external), the application (internal) and logging (internal)
RequestsInstrumentor().instrument()
FlaskInstrumentor().instrument_app(app)
# LoggingInstrumentor().instrument(set_logging_format=True, log_level=logging.DEBUG)

# Return B3 tracing headers: https://istio.io/latest/about/faq/distributed-tracing
def getForwardHeaders(request):
  headers = {}
  incoming_headers = [ 'x-request-id',
                        'x-b3-traceid',
                        'x-b3-spanid',
                        'x-b3-parentspanid',
                        'x-b3-sampled',
                        'x-b3-flags',
                        'x-ot-span-context' ]
  for ihdr in incoming_headers:
    val = request.headers.get(ihdr)
    if val is not None:
      headers[ihdr] = val
      if debug: print("incoming: " + ihdr + ":" + val, file = sys.stderr)
  return headers

@app.route('/')
def get_root():
  tracer = trace.get_tracer(__name__)
  with tracer.start_as_current_span("get_root()", context=extract(request.headers), kind=trace.SpanKind.CLIENT, attributes=collect_request_attributes(request.environ)) as root_span:
    headers = getForwardHeaders(request)
    # logger.info(msg = "B3 tracing headers: \n" + json.dumps(headers, sort_keys=True, indent=2))

    # Set custom tracing tags if defined in configfile
    if "tags" in pconf["tracing"] and not (pconf["tracing"]["tags"] is None):
      for key, value in pconf["tracing"]["tags"].items():
        root_span.set_attribute("_{}".format(key), value)

    if "upstream_host" in pconf["traffic"]:
      next_url = str(pconf["traffic"]["upstream_host"])
    else:
      next_url = ""

    # Only send next hop traffic if upstream host defined in configfile
    if not (next_url == "None") and next_url:
      with tracer.start_as_current_span("upstream()", context=extract(request.headers), kind=trace.SpanKind.CLIENT, attributes=collect_request_attributes(request.environ)) as upstream_span:
        upstream_span.set_attribute("_upstream_host", next_url)
        upstream_response = requests.get(url=next_url, headers=headers)
        response = json.loads(upstream_response.text)
        response.update({str(pconf["server"]["name"]): socket.gethostname()})
    else:
      response = {str(pconf["server"]["name"]): socket.gethostname()}
      root_span.add_event("Final hop reached!")
    
    # Add delay if enabled in configfile
    if "delay" in pconf["traffic"] and "enabled" in pconf["traffic"]["delay"] and "rate" in pconf["traffic"]["delay"] and "from" in pconf["traffic"]["delay"] and "to" in pconf["traffic"]["delay"]:
      if pconf["traffic"]["delay"]["enabled"]:
        with tracer.start_as_current_span("delay()", context=extract(request.headers), kind=trace.SpanKind.CLIENT, attributes=collect_request_attributes(request.environ)) as delay_span:
          if randint(0, 100) < pconf["traffic"]["delay"]["rate"]:
            delay_from = int(pconf["traffic"]["delay"]["from"])
            delay_to = int(pconf["traffic"]["delay"]["to"])
            delay = randint(delay_from, delay_to)
            delay_span.set_attribute("_delay", delay)
            if debug: print("Delay enabled... waiting {} seconds".format(delay))
            time.sleep(delay)

    # Add error code if enabled in configfile
    if "error" in pconf["traffic"] and "enabled" in pconf["traffic"]["error"] and "rate" in pconf["traffic"]["error"] and "code" in pconf["traffic"]["error"]:
      if pconf["traffic"]["error"]["enabled"]:
        with tracer.start_as_current_span("error()", context=extract(request.headers), kind=trace.SpanKind.CLIENT, attributes=collect_request_attributes(request.environ)) as error_span:
          if randint(0, 100) < pconf["traffic"]["error"]["rate"]:
            error_code = int(pconf["traffic"]["error"]["code"])
            error_span.set_attribute("_error", error_code)
            if debug: print("Error enabled... error code {}".format(error_code))
            return json.dumps(response, sort_keys=True, indent=2) + '\n', error_code

    return json.dumps(response, sort_keys=True, indent=2) + '\n', 200
    

def main(argv):

  # Start HTTP server
  arg_port = int(pconf["server"]["port"])
  app.run(debug=False,host='0.0.0.0',port=arg_port)


if __name__ == "__main__":
  main(sys.argv[1:])
