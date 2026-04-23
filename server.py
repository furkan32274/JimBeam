#!/usr/bin/env python3
"""
Jarvis Server — dein Mac als Jarvis-Server für iPhone und iPad.

Benutzung:
  python3 server.py          # HTTP (Mac + lokaler Chat)
  python3 server.py --https  # HTTPS (iPhone/iPad mit Mikrofon)
"""

import http.server
import socket
import socketserver
import ssl
import subprocess
import sys
import os


HTTP_PORT = 8080
HTTPS_PORT = 8443
CERT_FILE = 'jarvis-cert.pem'


def get_local_ip():
    """Return the MacBook's LAN IP so phones can reach it."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(('10.255.255.255', 1))
        return s.getsockname()[0]
    except Exception:
        return '127.0.0.1'
    finally:
        s.close()


def ensure_cert():
    if os.path.exists(CERT_FILE):
        return
    print('Erstelle selbstsigniertes HTTPS-Zertifikat…')
    subprocess.run([
        'openssl', 'req', '-x509', '-nodes',
        '-newkey', 'rsa:2048',
        '-keyout', CERT_FILE, '-out', CERT_FILE,
        '-days', '365',
        '-subj', '/CN=JarvisServer'
    ], check=True)


def print_banner(ip, port, proto):
    url_mac = f'{proto}://localhost:{port}/jarvis.html'
    url_lan = f'{proto}://{ip}:{port}/jarvis.html'
    bar = '═' * 58
    print()
    print(f'╔{bar}╗')
    print(f'║  JARVIS SERVER AKTIV' + ' ' * 37 + '║')
    print(f'╠{bar}╣')
    print(f'║  Auf diesem Mac:   {url_mac}' + ' ' * (37 - len(url_mac)) + '║')
    print(f'║  Auf iPhone/iPad:  {url_lan}' + ' ' * (37 - len(url_lan)) + '║')
    print(f'╠{bar}╣')
    print(f'║  iPhone/iPad muss im selben WLAN sein.' + ' ' * 19 + '║')
    if proto == 'https':
        print(f'║  Beim ersten Öffnen: "Details" → "Trotzdem besuchen"' + ' ' * 5 + '║')
    print(f'║  Strg+C zum Beenden' + ' ' * 38 + '║')
    print(f'╚{bar}╝')
    print()


def main():
    use_https = '--https' in sys.argv
    os.chdir(os.path.dirname(os.path.abspath(__file__)))

    ip = get_local_ip()
    port = HTTPS_PORT if use_https else HTTP_PORT
    proto = 'https' if use_https else 'http'

    handler = http.server.SimpleHTTPRequestHandler
    handler.extensions_map.update({'.js': 'application/javascript'})

    httpd = socketserver.TCPServer(('0.0.0.0', port), handler)
    httpd.allow_reuse_address = True

    if use_https:
        ensure_cert()
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx.load_cert_chain(CERT_FILE)
        httpd.socket = ctx.wrap_socket(httpd.socket, server_side=True)

    print_banner(ip, port, proto)

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print('\nServer gestoppt. Tschüss!')


if __name__ == '__main__':
    main()
