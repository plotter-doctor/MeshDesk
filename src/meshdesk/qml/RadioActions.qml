import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15

ScrollView {
    id: view; property var app; implicitWidth: 0; contentWidth: availableWidth; clip: true
    ColumnLayout {
        width: view.availableWidth; spacing: 12
        Label { textFormat: Text.PlainText; text: app ? app.tr("Radio controls") : "Radio controls"; font.pixelSize: 22; font.bold: true }
        Flow {
            Layout.fillWidth: true; spacing: 8; enabled: app && app.s.connected
            SpinBox { id: delay; from: 0; to: 86400; value: 10; editable: true; ToolTip.text: app ? app.tr("Delay in seconds") : "Delay in seconds"; ToolTip.visible: hovered }
            MeshButton { text: app ? app.tr("Reboot") : "Reboot"; onClicked: app.ask("Reboot radio in " + delay.value + " seconds","command",{name:ota.checked ? "reboot_ota" : "reboot",args:{value:delay.value}}) }
            CheckBox { id: ota; text: app.tr("Reboot into OTA mode") }
            MeshButton { text: app.tr("Cancel scheduled reboot"); onClicked: app.act("command",{name:ota.checked ? "reboot_ota" : "reboot",args:{value:-1}}) }
            MeshButton { text: app ? app.tr("Shutdown") : "Shutdown"; onClicked: app.ask("Shut down radio in " + delay.value + " seconds","command",{name:"shutdown",args:{value:delay.value}}) }
            MeshButton { text: app ? app.tr("Set current time") : "Set current time"; onClicked: app.act("command",{name:"set_time"}) }
            MeshButton { text: app ? app.tr("Enter DFU") : "Enter DFU"; onClicked: app.ask("Enter radio firmware update mode","command",{name:"dfu"}) }
        }
        Label { textFormat: Text.PlainText; text: app ? app.tr("Fixed position") : "Fixed position"; font.pixelSize: 19; font.bold: true }
        Flow {
            Layout.fillWidth: true; spacing: 8
            TextField { id: latitude; width: 150; placeholderText: app ? app.tr("Latitude") : "Latitude"; selectByMouse: true }
            TextField { id: longitude; width: 150; placeholderText: app ? app.tr("Longitude") : "Longitude"; selectByMouse: true }
            TextField { id: altitude; width: 140; placeholderText: app ? app.tr("Altitude (m)") : "Altitude (m)"; text: "0"; selectByMouse: true }
            MeshButton { text: app.tr("This computer"); onClicked: app.act("locate_host") }
            MeshButton { text: app ? app.tr("Set position") : "Set position"; enabled: app && app.s.connected; onClicked: app.ask("Set the radio's fixed position","command",{name:"fixed_position",args:{latitude:latitude.text,longitude:longitude.text,altitude:altitude.text}}) }
            MeshButton { text: app ? app.tr("Remove position") : "Remove position"; enabled: app && app.s.connected; onClicked: app.ask("Remove fixed position","command",{name:"remove_position"}) }
        }
        Label { textFormat: Text.PlainText; text: app ? app.tr("Canned messages") : "Canned messages"; font.pixelSize: 19; font.bold: true }
        TextArea { id: canned; Layout.fillWidth: true; placeholderText: app ? app.tr("Messages separated by |") : "Messages separated by |"; wrapMode: TextEdit.Wrap; selectByMouse: true }
        RowLayout {
            MeshButton { text: app ? app.tr("Read messages") : "Read messages"; enabled: app && app.s.connected; onClicked: app.act("command",{name:"canned_get"}) }
            MeshButton { text: app ? app.tr("Write messages") : "Write messages"; enabled: app && app.s.connected; onClicked: app.ask("Replace canned messages","command",{name:"canned_set",args:{value:canned.text}}) }
        }
        Label { textFormat: Text.PlainText; text: app ? app.tr("Ringtone") : "Ringtone"; font.pixelSize: 19; font.bold: true }
        TextArea { id: ringtone; Layout.fillWidth: true; placeholderText: app ? app.tr("RTTTL ringtone") : "RTTTL ringtone"; wrapMode: TextEdit.Wrap; selectByMouse: true }
        RowLayout {
            MeshButton { text: app ? app.tr("Read ringtone") : "Read ringtone"; enabled: app && app.s.connected; onClicked: app.act("command",{name:"ringtone_get"}) }
            MeshButton { text: app ? app.tr("Write ringtone") : "Write ringtone"; enabled: app && app.s.connected; onClicked: app.ask("Replace ringtone","command",{name:"ringtone_set",args:{value:ringtone.text}}) }
        }
        Connections {
            target: view.app
            function onSChanged() {
                if(!app)return;
                if(app.s.notification.message === "Computer location"){latitude.text=app.s.notification.latitude.toFixed(7);longitude.text=app.s.notification.longitude.toFixed(7);}
                if(app.s.notification.message === "canned_get")canned.text=app.s.notification.text || "";
                if(app.s.notification.message === "ringtone_get")ringtone.text=app.s.notification.text || "";
            }
        }
        Label { textFormat: Text.PlainText; text: app ? app.tr("Reset") : "Reset"; font.pixelSize: 19; font.bold: true; topPadding: 14 }
        Flow {
            Layout.fillWidth: true; spacing: 8; enabled: app && app.s.connected
            MeshButton { text: app ? app.tr("Reset node database") : "Reset node database"; onClicked: app.ask("Reset radio node database","command",{name:"reset_nodes"}) }
            MeshButton { width: Math.min(implicitWidth,parent.width); text: app ? app.tr("Factory reset configuration") : "Factory reset configuration"; onClicked: app.ask("Factory reset radio configuration","command",{name:"reset_config"}) }
            MeshButton { width: Math.min(implicitWidth,parent.width); text: app ? app.tr("Factory reset device") : "Factory reset device"; onClicked: app.ask("Factory reset entire radio","command",{name:"reset_device"}) }
        }
        Label { textFormat: Text.PlainText; text: app ? app.json(app.s.metadata) : ""; Layout.fillWidth: true; wrapMode: Text.Wrap; font.family: "monospace"; color: app ? app.muted : "gray" }
    }
}
