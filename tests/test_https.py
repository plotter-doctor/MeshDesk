from datetime import datetime,timedelta,timezone
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import ipaddress
import ssl
import threading
import pytest
import requests
from cryptography import x509
from cryptography.x509.oid import NameOID
from cryptography.hazmat.primitives import hashes,serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from meshdesk.radio import HTTPInterface


def test_https_rejects_untrusted_radio_certificate(tmp_path):
    key=rsa.generate_private_key(public_exponent=65537,key_size=2048)
    subject=x509.Name([x509.NameAttribute(NameOID.COMMON_NAME,'localhost')])
    certificate=(x509.CertificateBuilder().subject_name(subject).issuer_name(subject).public_key(key.public_key())
        .serial_number(x509.random_serial_number()).not_valid_before(datetime.now(timezone.utc)-timedelta(minutes=1))
        .not_valid_after(datetime.now(timezone.utc)+timedelta(days=1))
        .add_extension(x509.SubjectAlternativeName([x509.IPAddress(ipaddress.ip_address('127.0.0.1'))]),critical=False)
        .sign(key,hashes.SHA256()))
    cert=tmp_path/'cert.pem';private=tmp_path/'key.pem'
    cert.write_bytes(certificate.public_bytes(serialization.Encoding.PEM))
    private.write_bytes(key.private_bytes(serialization.Encoding.PEM,serialization.PrivateFormat.PKCS8,serialization.NoEncryption()))
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
    context=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER);context.load_cert_chain(cert,private)
    server.socket=context.wrap_socket(server.socket,server_side=True)
    worker=threading.Thread(target=server.serve_forever,daemon=True);worker.start()
    try:
        with pytest.raises(requests.exceptions.SSLError):HTTPInterface(f'https://127.0.0.1:{server.server_port}',timeout=1)
    finally:server.shutdown();server.server_close();worker.join(2)
