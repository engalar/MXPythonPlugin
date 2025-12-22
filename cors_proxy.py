import http.server
import socketserver
import urllib.request
import sys

# 配置
LOCAL_PORT = 19411           # 脚本监听的端口（给前端用这个）
JAEGER_URL = "http://localhost:9411" # 原始 Jaeger 地址

class CORSProxy(http.server.SimpleHTTPRequestHandler):
    def _send_cors_headers(self):
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header("Access-Control-Allow-Headers", "X-Requested-With, Content-Type, Accept, Origin, Authorization")

    def do_OPTIONS(self):
        self.send_response(200, "ok")
        self._send_cors_headers()
        self.end_headers()

    def do_POST(self):
        # 1. 获取请求体长度
        content_length = int(self.headers.get('Content-Length', 0))
        post_body = self.rfile.read(content_length)

        # 2. 构造转发给 Jaeger 的请求
        target_url = f"{JAEGER_URL}{self.path}"
        req = urllib.request.Request(target_url, data=post_body, method="POST")
        
        # 复制原请求的 Header (除了 Host)
        for key, value in self.headers.items():
            if key.lower() not in ['host', 'content-length']:
                req.add_header(key, value)

        try:
            # 3. 发送给 Jaeger
            with urllib.request.urlopen(req) as response:
                self.send_response(response.status)
                self._send_cors_headers() # 核心：注入 CORS 头
                self.end_headers()
                self.wfile.write(response.read())
        except urllib.error.HTTPError as e:
            self.send_response(e.code)
            self._send_cors_headers()
            self.end_headers()
            self.wfile.write(e.read())
        except Exception as e:
            self.send_response(500)
            self._send_cors_headers()
            self.end_headers()
            print(f"Error forwarding request: {e}")

if __name__ == "__main__":
    print(f"Starting CORS Proxy on port {LOCAL_PORT} -> forwarding to {JAEGER_URL}")
    print(f"Please configure your Jaeger Client to send traces to: http://localhost:{LOCAL_PORT}")
    with socketserver.TCPServer(("", LOCAL_PORT), CORSProxy) as httpd:
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nStopping proxy.")