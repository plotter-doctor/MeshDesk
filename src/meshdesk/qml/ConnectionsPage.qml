import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15

ScrollView {
    id: view
    property var app
    property string editingId: ""
    property string selectedTransport: ["serial","tcp","http","ble"][transport.currentIndex]
    property var matchingProfile: app ? (app.s.profiles.find(function(p) {return p.transport===view.selectedTransport && p.address===address.text.trim();}) || {}) : ({})
    property bool connectionActive: ["Connected","Connecting","Reconnecting"].indexOf(matchingProfile.status)>=0
    Component.onCompleted: {
        if (!app) return;
        var profile=app.s.profiles.find(function(p){return p.id===app.s.active;});
        if (profile && profile.id!=="simulator") {
            transport.currentIndex=["serial","tcp","http","ble"].indexOf(profile.transport);
            address.text=profile.address;profileName.text=profile.name;
        }
    }
    clip: true
    contentWidth: availableWidth
    ColumnLayout {
        width: view.availableWidth; spacing: 18
        Item { height: 4 }
        Label { textFormat: Text.PlainText; Layout.leftMargin: 24; Layout.rightMargin: 24; Layout.fillWidth: true; wrapMode: Text.Wrap; text: app ? app.tr("Connect your world") : "Connect your world"; font.pixelSize: 27; font.bold: true; color: app ? app.ink : "white" }
        Label { textFormat: Text.PlainText; Layout.leftMargin: 24; Layout.rightMargin: 24; Layout.fillWidth: true; text: app ? app.tr("Use a radio over USB, Wi-Fi or Bluetooth. Connections and conversations stay on this computer.") : "Use a radio over USB, Wi-Fi or Bluetooth. Connections and conversations stay on this computer."; wrapMode: Text.Wrap; color: app ? app.muted : "gray" }
        Frame {
            Layout.fillWidth: true; Layout.leftMargin: 24; Layout.rightMargin: 24
            ColumnLayout {
                anchors.fill: parent; spacing: 12
                RowLayout {
                    Layout.fillWidth: true
                    MeshComboBox { id: transport; objectName: "transportBox"; model: ["USB / serial", "TCP / Wi-Fi", "HTTP(S)", "Bluetooth LE"]; Layout.preferredWidth: 190 }
                    TextField { id: profileName; Layout.fillWidth: true; placeholderText: app ? app.tr("Connection name (optional)") : "Connection name (optional)" }
                }
                RowLayout {
                    Layout.fillWidth: true
                    TextField { id: address; objectName: "connectionAddress"; Layout.fillWidth: true; placeholderText: ["/dev/ttyUSB0 or COM3", "192.168.1.50:4403", "http://192.168.1.50", "Bluetooth address"][transport.currentIndex] }
                    MeshButton { objectName: "discoverRadios"; text: app ? app.tr("Discover") : "Discover"; enabled: app && !app.s.busy; visible: transport.currentIndex === 0 || transport.currentIndex === 3; onClicked: { app.act("scan", {transport:transport.currentIndex === 0 ? "serial" : "ble"}); portPicker.open(); } }
                }
                RowLayout {
                    visible: transport.currentIndex===3 && Qt.platform.os==="linux"
                    TextField { id: pairingPin; echoMode: TextInput.Password; maximumLength: 6; inputMethodHints: Qt.ImhDigitsOnly; placeholderText: app.tr("Six-digit radio PIN"); Layout.fillWidth: true }
                    MeshButton { text: app.tr("Pair Bluetooth"); enabled: pairingPin.text.length===6 && address.text.length>0 && !app.s.busy; onClicked: {app.act("ble_pair",{address:address.text,pin:pairingPin.text});pairingPin.clear();} }
                }
                RowLayout {
                    MeshButton {
                        objectName: "connectRadio"
                        text: app.tr(view.editingId ? "Save changes" : view.connectionActive ? (view.matchingProfile.status==="Connected" ? "Disconnect" : "Cancel connection") : "Connect radio")
                        highlighted: !view.connectionActive
                        enabled: address.text.trim().length>0 && app && (!app.s.busy || view.connectionActive)
                        onClicked: {
                            if (!view.editingId && view.connectionActive) app.act("disconnect",{id:view.matchingProfile.id});
                            else if (!view.editingId && view.matchingProfile.id) {app.act("select_profile",{id:view.matchingProfile.id});app.act("connect",{id:view.matchingProfile.id});}
                            else app.act(view.editingId ? "edit_profile" : "add_profile",{id:view.editingId,transport:view.selectedTransport,address:address.text,name:profileName.text});
                            view.editingId="";
                        }
                    }
                    MeshButton { text: app ? app.tr("Try local simulator") : "Try local simulator"; objectName: "startSimulator"; onClicked: { app.act("demo"); app.go("Chat"); } }
                }
                Label { textFormat: Text.PlainText; text: app.tr(view.matchingProfile.status || "Offline"); visible: !!view.matchingProfile.id; color: view.connectionActive ? app.accent : app.muted }
                Flow {
                    Layout.fillWidth: true; spacing: 6
                    MeshButton { text: app.tr("Test connection"); visible: transport.currentIndex===1 || transport.currentIndex===2; enabled: address.text.trim().length>0 && !app.s.busy; onClicked: app.act("probe",{transport:["serial","tcp","http","ble"][transport.currentIndex],address:address.text}) }
                    MeshButton { text: app.tr("Cancel"); visible: view.editingId.length>0; onClicked: {view.editingId="";profileName.clear();address.clear();} }
                }
            }
        }
        Label { textFormat: Text.PlainText; Layout.leftMargin: 24; text: app ? app.tr("SAVED CONNECTIONS") : "SAVED CONNECTIONS"; font.pixelSize: 11; font.letterSpacing: 1.5; color: app ? app.muted : "gray" }
        Repeater {
            model: app ? app.s.profiles : []
            delegate: Frame {
                Layout.fillWidth: true; Layout.leftMargin: 24; Layout.rightMargin: 24
                ColumnLayout {
                    anchors.fill: parent
                    RowLayout {
                        Layout.fillWidth: true
                        Label { textFormat: Text.PlainText; text: (modelData.is_default ? "★ " : "")+modelData.name; font.bold: true; font.pixelSize: 17; Layout.fillWidth: true; elide: Text.ElideRight }
                        MeshButton { text: app.tr(app.s.active===modelData.id ? "Selected" : "Select"); onClicked: app.act("select_profile",{id:modelData.id}) }
                        MeshToolButton { text: "⋯"; onClicked: profileMenu.open(); Menu {
                            id: profileMenu
                            MenuItem { text: app.tr("Edit connection"); enabled: modelData.id!=="simulator"; onTriggered: {view.editingId=modelData.id;profileName.text=modelData.name;address.text=modelData.address;transport.currentIndex=["serial","tcp","http","ble"].indexOf(modelData.transport);view.contentItem.contentY=0;} }
                            MenuItem { text: app.tr(modelData.is_default ? "Unset default" : "Set as default"); enabled: modelData.id!=="simulator"; onTriggered: app.act("default_profile",{id:modelData.is_default ? "" : modelData.id}) }
                            MenuItem { text: app.tr("Delete connection"); onTriggered: app.ask("Forget connection and its local history","forget",{id:modelData.id}) }
                        } }
                    }
                    Label { textFormat: Text.PlainText; text: modelData.transport.toUpperCase()+" · "+modelData.address+" · "+app.tr(modelData.status); font.pixelSize: 12; color: app.muted; Layout.fillWidth: true; wrapMode: Text.Wrap }
                    Label { textFormat: Text.PlainText; text: modelData.error || ""; visible: text.length>0; color: "#ffb796"; Layout.fillWidth: true; wrapMode: Text.Wrap }
                    RowLayout {
                        Label { textFormat: Text.PlainText; text: modelData.last_connected ? app.tr("Last connected")+": "+new Date(modelData.last_connected*1000).toLocaleString() : app.tr("Never connected"); color: app.muted; Layout.fillWidth: true; wrapMode: Text.Wrap; font.pixelSize: 11 }
                        MeshButton { property bool connected: ["Connected","Connecting","Reconnecting"].indexOf(modelData.status)>=0; text: app.tr(connected ? "Disconnect" : "Connect"); onClicked: app.act(connected ? "disconnect" : "connect",{id:modelData.id}) }
                    }
                }
            }
        }
        Item { height: 20 }
    }
    MeshDialog {
        id: portPicker; objectName: "portPicker"; modal: true
        parent: Overlay.overlay; anchors.centerIn: parent
        width: Math.min(parent.width-32,580); height: Math.min(parent.height-40,430)
        title: app.tr("Choose a radio"); standardButtons: Dialog.Cancel
        ColumnLayout {
            anchors.fill: parent
            Label { textFormat: Text.PlainText; text: app.s.busy ? app.tr("Searching for radios…") : app.tr("Select a port or Bluetooth radio"); Layout.fillWidth: true; wrapMode: Text.Wrap }
            CheckBox { id: allPorts; objectName: "showAllPorts"; text: app.tr("Show all serial ports"); visible: transport.currentIndex===0 }
            ListView {
                id: discovered; objectName: "discoveredRadioList"
                Layout.fillWidth: true; Layout.fillHeight: true; clip: true; spacing: 6
                model: app && app.s.notification.devices ? app.s.notification.devices.filter(function(d) {return allPorts.checked || d.likely;}) : []
                delegate: MeshButton {
                    objectName: "discoveredRadio"+index
                    width: discovered.width; height: 78
                    contentItem: Column {
                        spacing: 4
                        Text { width: parent.width; text: modelData.name; textFormat: Text.PlainText; color: app.ink; font.pixelSize: 14; elide: Text.ElideRight }
                        Text { width: parent.width; text: modelData.address; textFormat: Text.PlainText; color: app.muted; font.pixelSize: 12; elide: Text.ElideRight }
                        Text { width: parent.width; text: modelData.hint || ""; textFormat: Text.PlainText; color: app.muted; font.pixelSize: 11; elide: Text.ElideRight }
                    }
                    onClicked: {address.text=modelData.address;portPicker.close();}
                }
                Label { textFormat: Text.PlainText; anchors.centerIn: parent; visible: !app.s.busy && discovered.count===0; text: app.tr("No radios found"); color: app.muted }
                ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }
            }
        }
    }
}
