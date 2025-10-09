PostMessage("backend:clear", '')
def print(msg):
    PostMessage("backend:info",msg)
if token.IsCancellationRequested:
    print('cancel')
token.ThrowIfCancellationRequested()
import http.server
import socketserver
from datetime import datetime

PORT = 8080

class CustomHandler(http.server.BaseHTTPRequestHandler):
    """
    自定义 HTTP 请求处理器
    """
    
    def do_GET(self):
        
        if token.IsCancellationRequested:
            print('cancel')
        token.ThrowIfCancellationRequested()
        """
        处理所有 HTTP GET 请求
        """
        
        if self.path == '/hello':
            # 设置响应头
            self.send_response(200) # HTTP 状态码 OK
            self.send_header("Content-type", "text/html")
            self.end_headers()
            
            # 响应内容
            response_content = """
            <html>
            <head><title>Greeting</title></head>
            <body>
                <h1>Hello, World!</h1>
                <p>This is a custom response from my Python server.</p>
            </body>
            </html>
            """
            # 将内容编码为字节并发送
            self.wfile.write(response_content.encode('utf-8'))
            
        elif self.path == '/time':
            # 返回当前时间
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            message = f"Current server time is: {now}"
            
            self.send_response(200)
            self.send_header("Content-type", "text/plain")
            self.end_headers()
            
            self.wfile.write(message.encode('utf-8'))

        else:
            # 处理 404 错误
            self.send_response(404) # HTTP 状态码 Not Found
            self.send_header("Content-type", "text/plain")
            self.end_headers()
            self.wfile.write(b"404 Not Found")

def run_server():
    """运行自定义的 HTTP 服务器"""
    with socketserver.TCPServer(("", PORT), CustomHandler) as httpd:
        print(f"Custom server started on http://localhost:{PORT}")
        print("Try accessing /hello and /time")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nServer stopped.")
            httpd.shutdown()

run_server()