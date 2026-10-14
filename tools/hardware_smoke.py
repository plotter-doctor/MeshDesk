#!/usr/bin/env python3
"""Opt-in USB/GUI smoke test. No configuration writes or broadcast messages.

Reads settings through the real controller, operates the QML composer, and
records only device identifiers, timings and routing receipts (never keys).
Passing --message explicitly enables one private transmission to --recipient.
"""
import argparse
import json
import os
from pathlib import Path
import time


def resolve_recipient(nodes, query, local_num):
    query = query.strip().lower()
    if not query:
        raise ValueError('A recipient identifier or exact short name is required')
    matches = []
    for node in nodes:
        num = int(node['num'])
        user = node.get('user', {})
        identifier = f'{num:08x}'
        by_id = identifier == query.lstrip('!') if query.startswith('!') else (
            len(query) >= 4 and identifier.endswith(query))
        if by_id or str(user.get('shortName', '')).lower() == query:
            matches.append(node)
    if len(matches) != 1:
        raise ValueError(f'Recipient must identify exactly one known node; found {len(matches)}')
    if int(matches[0]['num']) in (local_num, 0, 0xffffffff):
        raise ValueError('Recipient must be a remote, unicast node')
    return matches[0]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', required=True)
    parser.add_argument('--data-dir', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--recipient', help='Unique node ID suffix (4+ digits) or exact short name')
    parser.add_argument('--message', help='Explicitly send this one private message using the GUI')
    parser.add_argument('--reply-to', type=int, default=0, help='Reply to a previous message packet ID')
    parser.add_argument('--skip-settings', action='store_true', help='Skip the full settings read on subsequent runs')
    parser.add_argument('--local-map-test', action='store_true', help='Exercise downloaded fixture tiles and real nodes without external map requests')
    parser.add_argument('--keep-open', action='store_true', help='Leave the connected GUI open after a successful test')
    parser.add_argument('--probe', choices=('telemetry', 'traceroute'), action='append', default=[],
                        help='Send this directed read-only request to the same recipient')
    parser.add_argument('--ack-timeout', type=float, default=90)
    args = parser.parse_args()
    if args.message is not None and not args.recipient:
        parser.error('--message requires --recipient')
    if args.probe and not args.recipient:
        parser.error('--probe requires --recipient')
    if not 0 <= args.reply_to <= 0xffffffff or (args.reply_to and args.message is None):
        parser.error('--reply-to must be a uint32 packet ID and requires --message')
    if not 1 <= args.ack_timeout <= 300:
        parser.error('--ack-timeout must be 1–300 seconds')
    if args.message is not None and (not args.message.strip() or len(args.message.encode()) > 233):
        parser.error('--message must contain 1–233 UTF-8 bytes')
    os.environ.setdefault('QT_QUICK_BACKEND', 'software')
    os.environ.setdefault('QT_QUICK_CONTROLS_STYLE', 'Material')
    from PyQt5.QtCore import QObject, QPointF, Qt, QUrl, qInstallMessageHandler
    from PyQt5.QtQml import QQmlApplicationEngine, qmlRegisterType
    from PyQt5.QtTest import QTest
    from PyQt5.QtWidgets import QApplication
    import meshdesk
    from meshdesk.controller import Controller
    from meshdesk.mapview import MeshMap, QRProvider
    from meshdesk.schema import sections
    from meshdesk.store import Store

    app = QApplication([])
    app.setApplicationName('MeshDesk hardware test')
    args.data_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    controller = Controller(Store(args.data_dir / 'meshdesk.sqlite3'))
    tile_server=None
    if args.local_map_test:
        from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
        from PyQt5.QtCore import QByteArray,QBuffer,QIODevice
        from PyQt5.QtGui import QImage,QColor
        import threading
        image=QImage(256,256,QImage.Format_RGB32);image.fill(QColor('#314e61'))
        raw=QByteArray();buffer=QBuffer(raw);buffer.open(QIODevice.WriteOnly);image.save(buffer,'PNG');buffer.close()
        class TileHandler(BaseHTTPRequestHandler):
            def log_message(self,*args):pass
            def do_GET(self):
                self.send_response(200);self.send_header('Content-Type','image/png');self.end_headers()
                try:self.wfile.write(bytes(raw))
                except (BrokenPipeError,ConnectionResetError):pass
        tile_server=ThreadingHTTPServer(('127.0.0.1',0),TileHandler)
        threading.Thread(target=tile_server.serve_forever,daemon=True).start()
        controller.store.put('tile_url',f'http://127.0.0.1:{tile_server.server_port}/{{z}}/{{x}}/{{y}}.png')
        controller.store.put('online_maps',False);controller._publish()
    report = {'started_utc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
              'transport': 'serial', 'port': args.port, 'settings': [], 'routing_receipts': [],
              'configuration_writes': 0, 'messages_sent': 0}
    qml_messages = []
    probe_packets = []
    command_results = {}
    previous_handler = qInstallMessageHandler(lambda kind, context, text: qml_messages.append(text))
    engine = QQmlApplicationEngine()
    qmlRegisterType(MeshMap, 'MeshDesk', 1, 0, 'MeshMap')
    engine.rootContext().setContextProperty('bridge', controller)
    engine.addImageProvider('qr', QRProvider(controller))
    engine.load(QUrl.fromLocalFile(str(Path(meshdesk.__file__).parent / 'qml' / 'Main.qml')))

    def act(action, **kwargs):
        controller.dispatch(action, json.dumps(kwargs))
        app.processEvents()

    def wait_for(condition, timeout=20):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            app.processEvents()
            if condition():
                return
            QTest.qWait(20)
        raise TimeoutError('Timed out waiting for hardware/UI operation')

    def packet_event(pid, generation, kind, data):
        if kind == 'result' and data.get('operation', '').startswith('command:'):
            command_results[data['operation']] = data['value']
        if kind != 'packet':
            return
        decoded = data.get('decoded', {})
        if decoded.get('portnum') == 'ROUTING_APP':
            report['routing_receipts'].append({
                'from': data.get('from'), 'to': data.get('to'),
                'request_id': decoded.get('requestId'),
                'error': decoded.get('routing', {}).get('errorReason', 'NONE'),
                'rx_snr': data.get('rxSnr'), 'rx_rssi': data.get('rxRssi'),
                'received_utc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())})
        elif decoded.get('portnum') in ('TELEMETRY_APP', 'TRACEROUTE_APP'):
            probe_packets.append(data)

    controller.delivered.connect(packet_event)
    exit_code = 1
    try:
        if not engine.rootObjects():
            raise RuntimeError('Could not create the QML window')
        root = engine.rootObjects()[0]
        existing = next((p for p in controller.store.profiles()
                         if p['transport'] == 'serial' and p['address'] == args.port), None)
        started = time.monotonic()
        if existing:
            act('select_profile', id=existing['id'])
            act('connect')
        else:
            act('add_profile', transport='serial', address=args.port, name='USB radio')
        pid = controller.active
        wait_for(lambda: controller.sessions[pid]['status'] == 'Connected')
        snapshot = controller.sessions[pid]['snapshot']
        local_num = snapshot['my_num']
        report.update(connect_seconds=round(time.monotonic() - started, 3),
                      local_id=f'!{local_num:08x}', metadata=snapshot['metadata'],
                      node_count=len(snapshot['nodes']))
        print('Connected:', report['local_id'], report['metadata'].get('firmware_version'), flush=True)
        recipient = resolve_recipient(snapshot['nodes'], args.recipient, local_num) if args.recipient else None
        if recipient:
            report['recipient'] = {'id': f"!{recipient['num']:08x}",
                                   'short_name': recipient.get('user', {}).get('shortName')}
            print('Resolved recipient:', report['recipient'], flush=True)
        for section in ([] if args.skip_settings else sections()):
            started = time.monotonic()
            act('setting_load', section=section['key'])
            wait_for(lambda: not controller.settings_loading and not controller.busy)
            error = controller.settings_error
            status = 'unavailable' if error.startswith('This firmware does not expose ') else ('failed' if error else 'passed')
            report['settings'].append({'section': section['key'], 'status': status,
                                       'seconds': round(time.monotonic() - started, 3), 'error': error})
            print('Read', section['key'], status, flush=True)
        for page in ('Chat', 'Nodes', 'Map', 'Settings', 'Connections', 'Activity', 'Preferences'):
            root.setProperty('page', page)
            QTest.qWait(150)
        report['pages_opened'] = 7
        if args.local_map_test:
            import gc
            act('preference',key='online_maps',value=True)
            tile_counts=[];hovered=0
            for _ in range(3):
                root.setProperty('page','Map');QTest.qWait(100);root.grabWindow();gc.collect()
                QTest.qWait(250)
                item=root.findChild(QObject,'meshMap')
                wait_for(lambda:bool(item._images),timeout=20)
                tile_counts.append(len(item._images));root.grabWindow()
                for x,y,num in item._markers[:5]:
                    QTest.mouseMove(root,item.mapToScene(QPointF(x,y)).toPoint());QTest.qWait(30)
                    if item.infoAt(x,y):hovered+=1
                del item
                root.setProperty('page','Nodes');gc.collect();QTest.qWait(150)
            report['local_map_test']={'cycles':3,'decoded_tiles':tile_counts,'node_hover_checks':hovered,'provider':'local fixture; no external map requests'}
        if args.message is not None:
            root.setProperty('page', 'Chat')
            act('chat', peer=recipient['num'], channel=0)
            QTest.qWait(200)
            composer = root.findChild(QObject, 'composer')
            send = root.findChild(QObject, 'sendMessage')
            if composer is None or send is None:
                raise RuntimeError('Composer or send button is missing')
            composer.setProperty('text', args.message)
            if args.reply_to:
                root.findChild(QObject, 'pageLoader').property('item').setProperty('replyId', str(args.reply_to))
            QTest.qWait(100)
            started = time.time()
            point = send.mapToScene(QPointF(send.width() / 2, send.height() / 2)).toPoint()
            QTest.mouseClick(root, Qt.LeftButton, pos=point)

            def sent_message():
                return next((m for m in controller.store.messages(pid, recipient['num'])
                             if m['outgoing'] and m['timestamp'] >= started and m['text'] == args.message), None)

            wait_for(lambda: sent_message() is not None)
            sent = sent_message()
            report.update(messages_sent=1, packet_id=sent['packet_id'], reply_to=args.reply_to,
                          message_utf8_bytes=len(args.message.encode()))
            print('Private message submitted:', sent['packet_id'], flush=True)
            deadline = time.monotonic() + args.ack_timeout
            while time.monotonic() < deadline:
                QTest.qWait(100)
                receipts = [r for r in report['routing_receipts'] if r['request_id'] == sent['packet_id']]
                remote = [r for r in receipts if r['from'] == recipient['num'] and r['to'] == local_num and r['error'] in ('NONE', 0)]
                if remote or any(r['error'] not in ('NONE', 0) for r in receipts):
                    break
            report['message_status'] = sent_message()['status']
            report['remote_acknowledged'] = bool(remote)
            report['message_receipts'] = receipts
            print('Message result:', json.dumps({'status': report['message_status'], 'remote_acknowledged': bool(remote), 'receipts': receipts}), flush=True)
            root.setProperty('toastText', '')
            QTest.qWait(150)
            root.grabWindow().save(str(args.output.with_suffix('.png')))
        report['probes'] = []
        for probe in args.probe:
            before = len(probe_packets)
            command_results.pop('command:' + probe, None)
            act('command', name=probe, args={'node': recipient['num']})
            wait_for(lambda: not controller.busy)
            result = command_results.get('command:' + probe, {})
            sent_ids = [result['packet_id']] if 'packet_id' in result else []
            port = 'TELEMETRY_APP' if probe == 'telemetry' else 'TRACEROUTE_APP'
            def response():
                return next((p for p in probe_packets[before:] if p.get('from') == recipient['num']
                             and p.get('to') == local_num and p.get('decoded', {}).get('portnum') == port
                             and p['decoded'].get('requestId') in sent_ids), None)
            try:
                wait_for(lambda: response() is not None, timeout=args.ack_timeout)
            except TimeoutError:
                pass
            packet = response()
            result = {'operation': probe, 'responded': packet is not None, 'request_ids': sent_ids}
            if packet:
                result.update(pki_encrypted=packet.get('pkiEncrypted', False),
                              rx_snr=packet.get('rxSnr'), rx_rssi=packet.get('rxRssi'))
            report['probes'].append(result)
            print('Probe:', json.dumps(result), flush=True)
        # A clean close/open verifies port reuse and a fresh settings handshake.
        old_radio = controller.sessions[pid]['radio']
        act('disconnect')
        wait_for(lambda: old_radio.interface is None or old_radio.interface.stream is None or not old_radio.interface.stream.is_open)
        act('connect')
        wait_for(lambda: controller.sessions[pid]['status'] == 'Connected')
        report['reconnected_same_node'] = controller.sessions[pid]['snapshot']['my_num'] == local_num
        root.setProperty('page', 'Chat')
        if recipient:
            act('chat', peer=recipient['num'], channel=0)
        QTest.qWait(300)
        report['qml_errors'] = [m for m in qml_messages if any(t in m for t in ('Error', 'Cannot', 'Unable', 'is not', 'not found', 'Unexpected', 'Invalid', 'Binding loop'))]
        report['passed'] = (not report['qml_errors'] and report['reconnected_same_node']
                            and not any(s['status'] == 'failed' for s in report['settings'])
                            and all(p['responded'] for p in report['probes'])
                            and (args.message is None or report.get('remote_acknowledged', False)))
        exit_code = 0 if report['passed'] else 1
        if args.keep_open and report['passed']:
            root.setProperty('page', 'Chat')
            if recipient:
                act('chat', peer=recipient['num'], channel=0)
            root.setProperty('toastText', '')
            saved = {k: v for k, v in report.items() if k != 'routing_receipts'}
            args.output.write_text(json.dumps(saved, indent=2) + '\n', encoding='utf-8')
            # The measurement is finished; do not keep accumulating packet or
            # QML diagnostic lists during normal interactive use.
            controller.delivered.disconnect(packet_event)
            qInstallMessageHandler(previous_handler)
            print('Hardware test passed; GUI remains connected. Close the window to exit.', flush=True)
            app.exec_()
    except Exception as error:
        report['error'] = str(error)
        report['passed'] = False
        print(type(error).__name__ + ':', str(error), flush=True)
    finally:
        # Admin ACKs are intentionally omitted from the saved report.
        report.pop('routing_receipts', None)
        args.output.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
        for window in engine.rootObjects():
            window.close()
        del engine
        controller.close()
        if tile_server:tile_server.shutdown();tile_server.server_close()
        qInstallMessageHandler(previous_handler)
    return exit_code


if __name__ == '__main__':
    raise SystemExit(main())
