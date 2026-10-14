#!/usr/bin/env python3
"""Exercise HTTPS using the Qt DLLs in an extracted Windows release bundle."""
import argparse
import ctypes
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import ipaddress
import json
import os
from pathlib import Path
import ssl
import sys
import tempfile
import threading
import types


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('bundle', type=Path)
    parser.add_argument('--output', type=Path, default=Path('artifacts/windows/tls-report.json'))
    args = parser.parse_args()
    root = args.bundle.resolve() / '_internal'
    assert sys.platform == 'win32'
    # Import the shipped extension modules, with no separately installed PyQt.
    # Match PyQt5 5.15.11's find_qt() and PyInstaller's Qt runtime hook:
    # Qt's QSystemLibrary searches PATH, independently of AddDllDirectory.
    os.environ['PATH'] = os.pathsep.join((str(root / 'PyQt5/Qt5/bin'),
                                         str(root), os.environ.get('PATH', '')))
    handles = [os.add_dll_directory(str(root)),
               os.add_dll_directory(str(root / 'PyQt5/Qt5/bin'))]
    package = types.ModuleType('PyQt5')
    package.__path__ = [str(root / 'PyQt5')]
    # QtCore uses the package location when installing its embedded qt.conf.
    # PyInstaller keeps this Python module inside its archive, so supply the
    # location it would have in the extracted bundle.
    package.__file__ = str(root / 'PyQt5/__init__.py')
    sys.modules['PyQt5'] = package
    from PyQt5 import QtCore, QtNetwork, QtGui
    assert Path(QtNetwork.__file__).is_relative_to(root)
    app = QtCore.QCoreApplication([])
    assert QtNetwork.QSslSocket.supportsSsl(), 'Packaged Qt cannot load TLS'
    from cryptography import x509
    from cryptography.x509.oid import NameOID
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'localhost')])
    cert = (x509.CertificateBuilder().subject_name(subject).issuer_name(subject)
            .public_key(key.public_key()).serial_number(x509.random_serial_number())
            .not_valid_before(datetime.now(timezone.utc) - timedelta(minutes=1))
            .not_valid_after(datetime.now(timezone.utc) + timedelta(days=1))
            .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
            .add_extension(x509.SubjectAlternativeName([
                x509.IPAddress(ipaddress.ip_address('127.0.0.1'))]), critical=False)
            .sign(key, hashes.SHA256()))
    pem = cert.public_bytes(serialization.Encoding.PEM)
    image = QtGui.QImage(256, 256, QtGui.QImage.Format_RGB32)
    image.fill(QtGui.QColor('#173846'))
    raw = QtCore.QByteArray()
    buffer = QtCore.QBuffer(raw)
    buffer.open(QtCore.QIODevice.WriteOnly)
    assert image.save(buffer, 'PNG')
    buffer.close()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            self.send_response(200)
            self.send_header('Content-Type', 'image/png')
            self.end_headers()
            self.wfile.write(bytes(raw))

    with tempfile.TemporaryDirectory(prefix='meshdesk-tls-') as directory:
        cert_file = Path(directory) / 'cert.pem'
        key_file = Path(directory) / 'key.pem'
        cert_file.write_bytes(pem)
        key_file.write_bytes(key.private_bytes(serialization.Encoding.PEM,
                            serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
        server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(cert_file, key_file)
        server.socket = context.wrap_socket(server.socket, server_side=True)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        manager = QtNetwork.QNetworkAccessManager()

        def request(trusted):
            request = QtNetwork.QNetworkRequest(QtCore.QUrl(f'https://127.0.0.1:{server.server_port}/tile.png'))
            configuration = QtNetwork.QSslConfiguration.defaultConfiguration()
            configuration.setCaCertificates([QtNetwork.QSslCertificate(pem)] if trusted else [])
            request.setSslConfiguration(configuration)
            reply = manager.get(request)
            loop = QtCore.QEventLoop()
            timer = QtCore.QTimer()
            timer.setSingleShot(True)
            timer.timeout.connect(loop.quit)
            reply.finished.connect(loop.quit)
            timer.start(15000)
            loop.exec_()
            assert reply.isFinished(), 'TLS request timed out'
            result = reply.error(), bytes(reply.readAll()), reply.errorString()
            reply.deleteLater()
            app.processEvents()
            return result

        try:
            bad, _, _ = request(False)
            assert bad == QtNetwork.QNetworkReply.SslHandshakeFailedError
            error, data, message = request(True)
            assert error == QtNetwork.QNetworkReply.NoError, message
            decoded = QtGui.QImage.fromData(data)
            assert decoded.size() == QtCore.QSize(256, 256)
            assert decoded.pixelColor(10, 10) == QtGui.QColor('#173846')
        finally:
            server.shutdown()
            server.server_close()
            thread.join(2)
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.GetModuleHandleW.restype = ctypes.c_void_p
    kernel.GetModuleHandleW.argtypes = [ctypes.c_wchar_p]
    kernel.GetModuleFileNameW.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_uint]
    loaded = {}
    for library in ('Qt5Network.dll', 'libssl-1_1-x64.dll', 'libcrypto-1_1-x64.dll'):
        handle = kernel.GetModuleHandleW(library)
        assert handle, library
        path = ctypes.create_unicode_buffer(32768)
        assert kernel.GetModuleFileNameW(handle, path, len(path))
        assert Path(path.value).resolve().is_relative_to(root), path.value
        loaded[library] = path.value
    report = {'qt_tls': QtNetwork.QSslSocket.sslLibraryVersionString(),
              'trusted_https_tile': True, 'untrusted_certificate_rejected': True,
              'loaded_libraries': loaded}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
