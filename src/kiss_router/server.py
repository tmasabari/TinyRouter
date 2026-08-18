import argparse
import asyncio
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from .client import ChatClient
from .config import load_config
from .orchestrator import Orchestrator


class Handler(BaseHTTPRequestHandler):
    router: Orchestrator

    def do_POST(self):
        if self.path != "/v1/chat/completions":
            self.send_error(404)
            return
        try:
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length))
            if not isinstance(body, dict):
                raise ValueError("request body must be an object")
            messages = body.get("messages")
            if not isinstance(messages, list) or not messages or not all(
                isinstance(m, dict) and isinstance(m.get("role"), str) and isinstance(m.get("content"), str)
                for m in messages
            ):
                raise ValueError("messages must contain role and string content")
            result = asyncio.run(self.router.handle(messages))
            self._json(200, {
                "id": f"chatcmpl-{result.event.request_id}",
                "object": "chat.completion",
                "choices": [{"index": 0, "message": {"role": "assistant", "content": result.response.content}, "finish_reason": "stop"}],
                "model": result.response.model,
                "usage": {
                    "prompt_tokens": result.response.input_tokens or 0,
                    "completion_tokens": result.response.output_tokens or 0,
                    "total_tokens": (result.response.input_tokens or 0) + (result.response.output_tokens or 0),
                },
<<<<<<< HEAD
            })
=======
            }, result.event)
>>>>>>> origin/main
        except (ValueError, json.JSONDecodeError) as error:
            self._json(400, {"error": {"message": str(error), "type": "invalid_request_error"}})
        except Exception as error:
            self._json(502, {"error": {"message": str(error), "type": "upstream_error"}})

    def log_message(self, format, *args):
        return

<<<<<<< HEAD
    def _json(self, status, payload):
=======
    def _json(self, status, payload, event=None):
>>>>>>> origin/main
        data = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
<<<<<<< HEAD
=======
        if event:
            self.send_header("X-TinyRouter-Route", event.route)
            self.send_header("X-TinyRouter-Source", event.source)
            self.send_header("X-TinyRouter-Model", event.model)
            self.send_header("X-TinyRouter-L1-Latency-Ms", str(event.l1_latency_ms))
            self.send_header("X-TinyRouter-Total-Latency-Ms", str(event.latency_ms))
            self.send_header("X-TinyRouter-Escalation", str(event.escalation).lower())
>>>>>>> origin/main
        self.end_headers()
        self.wfile.write(data)


def main():
    parser = argparse.ArgumentParser(description="KISS local AI router")
    parser.add_argument("--config", default="config/router.yaml")
    args = parser.parse_args()
    config = load_config(args.config)
    Handler.router = Orchestrator(config, ChatClient())
    server = ThreadingHTTPServer((config.server.host, config.server.port), Handler)
    print(f"TinyRouter listening on http://{config.server.host}:{config.server.port}/v1/chat/completions")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
