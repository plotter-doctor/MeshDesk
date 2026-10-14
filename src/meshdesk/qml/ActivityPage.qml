import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15

Item {
    id: view; property var app
    property var notice: app ? app.s.notification_view || {} : ({})
    ColumnLayout {
        anchors.fill: parent; anchors.margins: 20; spacing: 12
        RowLayout {
            Label { textFormat: Text.PlainText; text: app ? app.tr("Activity") : "Activity"; font.pixelSize: 25; font.bold: true; Layout.fillWidth: true }
            MeshButton { text: app ? app.tr("Export") : "Export"; onClicked: app.act("export",{kind:"activity"}) }
        }
        Frame {
            Layout.fillWidth: true; visible: app && Object.keys(app.s.notification).length > 0
            ColumnLayout {
                anchors.fill: parent
                Label { textFormat: Text.PlainText; text: view.notice.title || (app ? app.s.notification.message || app.tr("Radio notification") : ""); font.bold: true; Layout.fillWidth: true; wrapMode: Text.Wrap }
                Label { textFormat: Text.PlainText; visible: !!view.notice.description; text: view.notice.description || ""; Layout.fillWidth: true; wrapMode: Text.Wrap }
                Label { textFormat: Text.PlainText; visible: !!view.notice.code; text: view.notice.code || ""; font.pixelSize: 28; font.bold: true; font.letterSpacing: 4; color: app.accent }
                ScrollView {
                    implicitWidth: 0; contentWidth: availableWidth
                    Layout.fillWidth: true; Layout.preferredHeight: Math.min(170,notificationText.implicitHeight); clip: true
                    TextArea { id: notificationText; text: view.notice.rows && view.notice.rows.length ? view.notice.rows.map(function(r){return r.name+" "+r.value;}).join("\n") : view.notice.title ? "" : app ? app.s.notification.details || app.json(app.s.notification) : ""; readOnly: true; selectByMouse: true; wrapMode: TextEdit.Wrap; font.pixelSize: 12 }
                }
                Flow {
                    Layout.fillWidth: true; spacing: 6
                    MeshButton { text: app ? app.tr("Dismiss") : "Dismiss"; onClicked: app.act("dismiss_notification") }
                    MeshButton { text: app ? app.tr("Enter security number") : "Enter security number"; visible: app && !!app.s.notification.key_verification_number_request; onClicked: verifyDialog.open() }
                    MeshButton { text: app ? app.tr("Characters match · verify") : "Characters match · verify"; visible: app && !!app.s.notification.key_verification_final; onClicked: app.act("verify_reply",{accept:true}) }
                    MeshButton { text: app ? app.tr("Reject") : "Reject"; visible: app && !!app.s.notification.key_verification_final; onClicked: app.act("verify_reply",{accept:false}) }
                }
            }
        }
        TextField { id: search; Layout.fillWidth: true; placeholderText: app ? app.tr("Filter packets, telemetry and radio logs…") : "Filter packets, telemetry and radio logs…" }
        ListView {
            id: events; Layout.fillWidth: true; Layout.fillHeight: true; clip: true; spacing: 8
            model: app ? app.s.events : []
            delegate: Frame {
                width: events.width; visible: (modelData.kind + modelData.summary).toLowerCase().indexOf(search.text.toLowerCase()) >= 0; height: visible ? content.implicitHeight+24 : 0
                ColumnLayout {
                    id: content; width: parent.width
                    Label { textFormat: Text.PlainText; text: modelData.time + " · " + modelData.kind; color: app ? app.accent : "white"; font.bold: true }
                    Label { text: modelData.summary; textFormat: Text.PlainText; wrapMode: Text.WrapAnywhere; Layout.fillWidth: true; font.family: "monospace"; font.pixelSize: 11; maximumLineCount: 6; elide: Text.ElideRight }
                    MeshButton { text: app ? app.tr("Copy full event") : "Copy full event"; flat: true; onClicked: app.act("copy",{text:app.json(modelData.data)}) }
                }
            }
            ScrollBar.vertical: ScrollBar {}
        }
    }
    MeshDialog {
        id: verifyDialog; objectName: "verifyDialog"; width: Math.min(parent.width-30,400); title: app ? app.tr("Verify node identity") : "Verify node identity"; modal: true; anchors.centerIn: parent; standardButtons: Dialog.Ok | Dialog.Cancel
        ColumnLayout {
            Label { textFormat: Text.PlainText; text: app ? app.tr("Enter the security number shown by the other node.") : "Enter the security number shown by the other node."; wrapMode: Text.Wrap; Layout.maximumWidth: 320 }
            TextField { id: number; placeholderText: app ? app.tr("Security number") : "Security number"; inputMethodHints: Qt.ImhDigitsOnly }
        }
        onAccepted: app.act("verify_reply",{number:number.text})
    }
}
