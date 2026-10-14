import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15

Item {
    id: view
    property var app
    property string replyId: "0"
    property string replyText: ""
    property bool conversationsVisible: !app || !app.compact
    RowLayout {
        anchors.fill: parent; spacing: 0
        Rectangle {
            Layout.fillHeight: true; Layout.preferredWidth: app && app.compact ? 155 : 230
            color: app ? app.bg : "#101b24"
            visible: !app || !app.compact || view.conversationsVisible
            ColumnLayout {
                anchors.fill: parent; anchors.margins: 14; spacing: 14
                Label { textFormat: Text.PlainText; text: app ? app.tr("Conversations") : "Conversations"; Layout.fillWidth: true; elide: Text.ElideRight; font.pixelSize: app && app.compact ? 14 : 20; font.bold: true }
                TextField { id: conversationSearch; Layout.fillWidth: true; placeholderText: app ? app.tr("Find a conversation…") : "Find a conversation…" }
                ListView {
                    Layout.fillWidth: true; Layout.fillHeight: true; clip: true
                    model: app ? app.s.conversations : []
                    delegate: ItemDelegate {
                        width: ListView.view.width; height: visible ? 65 : 0
                        visible: modelData.name.toLowerCase().indexOf(conversationSearch.text.toLowerCase()) >= 0
                        highlighted: app.s.peer === modelData.peer && app.s.channel === modelData.channel
                        onClicked: { app.act("draft",{text:composer.text}); messages.followLatest=true; app.act("chat",{peer:modelData.peer,channel:modelData.channel}); replyId="0"; replyText=""; if(app.compact)view.conversationsVisible=false; Qt.callLater(messages.followEnd); }
                        contentItem: RowLayout {
                            Rectangle { width: 34; height: 34; radius: 10; color: highlighted ? "#366755" : "#26404c"; Label { textFormat: Text.PlainText; anchors.centerIn: parent; text: modelData.peer ? modelData.name.substring(0,2).toUpperCase() : "#"; color: "#a1e8cd"; font.bold: true } }
                            ColumnLayout {
                                Layout.fillWidth: true; spacing: 3
                                Label { textFormat: Text.PlainText; Layout.fillWidth: true; text: modelData.name; elide: Text.ElideRight; font.bold: modelData.unread > 0 }
                                Label { textFormat: Text.PlainText; text: modelData.peer ? "Direct message" : "Channel " + modelData.channel; font.pixelSize: 11; color: app.muted }
                            }
                            Label { textFormat: Text.PlainText; text: modelData.unread || ""; color: app.accent }
                        }
                    }
                    ScrollBar.vertical: ScrollBar {}
                }
                MeshButton { text: app ? app.tr("+ Connect a radio") : "+ Connect a radio"; Layout.fillWidth: true; onClicked: app.go("Connections") }
            }
        }
        Rectangle {
            Layout.fillWidth: true; Layout.fillHeight: true; color: app ? app.panel : "#172733"
            ColumnLayout {
                anchors.fill: parent; anchors.margins: 18; spacing: 10
                RowLayout {
                    Layout.fillWidth: true; Layout.minimumWidth: 0
                    MeshToolButton { text: "‹"; visible: app && app.compact; onClicked: view.conversationsVisible = !view.conversationsVisible }
                    ColumnLayout {
                        Layout.fillWidth: true; Layout.minimumWidth: 0; spacing: 2
                        Label { Layout.fillWidth: true; Layout.minimumWidth: 0; elide: Text.ElideRight; textFormat: Text.PlainText; text: app ? app.s.chat_name : "Messages"; font.pixelSize: 23; font.bold: true }
                        Label { Layout.fillWidth: true; Layout.minimumWidth: 0; wrapMode: Text.Wrap; visible: !app || !app.keyboardOpen; textFormat: Text.PlainText; text: app && app.s.connected ? "Connected · local history enabled" : "Connect a radio to start messaging"; color: app ? app.muted : "gray"; font.pixelSize: 12 }
                    }
                    MeshToolButton { text: "↓"; ToolTip.text: app ? app.tr("Export messages") : "Export messages"; ToolTip.visible: hovered; onClicked: app.act("export",{kind:"messages"}) }
                    MeshToolButton { text: "×"; ToolTip.text: app ? app.tr("Delete conversation") : "Delete conversation"; ToolTip.visible: hovered; onClicked: app.ask("Delete this conversation", "delete_messages") }
                }
                TextField { id: messageSearch; visible: !app || !app.keyboardOpen || activeFocus; Layout.fillWidth: true; placeholderText: app ? app.tr("Search message history") : "Search message history"; onTextChanged: if(app)app.act("search",{text:text}) }
                ListView {
                    id: messages; objectName: "messageList"
                    property bool followLatest: true
                    function followEnd() { if(followLatest && !moving)positionViewAtEnd(); }
                    Layout.fillWidth: true; Layout.fillHeight: true; clip: true; spacing: 12
                    model: app ? app.s.messages : []
                    header: Row { MeshButton { text: app ? app.tr("Older") : "Older"; visible: messages.count >= 100; onClicked: app.act("older") } MeshButton { text: app ? app.tr("Newer") : "Newer"; visible: app && app.s.history_offset > 0; onClicked: app.act("newer") } }
                    onCountChanged: Qt.callLater(followEnd)
                    onContentHeightChanged: Qt.callLater(followEnd)
                    onMovementStarted: followLatest=false
                    onMovementEnded: followLatest=atYEnd
                    delegate: Item {
                        width: messages.width; height: bubble.height
                        TextMetrics { id: messageMetrics; font: body.font; text: modelData.text }
                        Rectangle {
                            id: bubble
                            width: Math.min(parent.width * 0.9, Math.max(230, messageMetrics.advanceWidth + 30))
                            height: bubbleLayout.implicitHeight + 22
                            anchors.right: modelData.outgoing ? parent.right : undefined
                            color: modelData.outgoing ? "#245044" : (app.s.theme === "light" ? "#e5eef1" : "#243846")
                            radius: 12
                            Column {
                                id: bubbleLayout; anchors.left: parent.left; anchors.right: parent.right; anchors.top: parent.top; anchors.margins: 12; spacing: 6
                                Label { textFormat: Text.PlainText; text: modelData.outgoing ? "You" : modelData.sender_name; color: modelData.outgoing ? "#93e9c8" : app.accent; font.bold: true; font.pixelSize: 12 }
                                Label { textFormat: Text.PlainText; width: parent.width; wrapMode: Text.Wrap; visible: !!modelData.metadata.reply_id; text: "↪ Reply to #" + modelData.metadata.reply_id; color: "#a5bcc5"; font.pixelSize: 10 }
                                Label { id: body; text: modelData.text; textFormat: Text.PlainText; wrapMode: Text.Wrap; width: parent.width; color: modelData.outgoing ? "#f1fffa" : app.ink; font.pixelSize: 15 }
                                RowLayout {
                                    width: parent.width
                                    Label { textFormat: Text.PlainText; text: modelData.time + " · " + app.tr(modelData.status) + (modelData.metadata.pki ? " · PKI" : ""); color: modelData.outgoing ? "#b4d6c9" : app.muted; font.pixelSize: 10; Layout.fillWidth: true; wrapMode: Text.Wrap }
                                    MeshToolButton { text: "↪"; implicitHeight: 30; implicitWidth: 32; onClicked: { replyId=String(modelData.packet_id);replyText=modelData.text;composer.forceActiveFocus(); } }
                                    MeshToolButton { text: "⋯"; implicitHeight: 30; implicitWidth: 32; onClicked: messageMenu.popup(); Menu {
                                        id: messageMenu
                                        MenuItem { text: app ? app.tr("Copy text") : "Copy text"; onTriggered: app.act("copy",{text:modelData.text}) }
                                        MenuItem { text: app ? app.tr("Delete message") : "Delete message"; onTriggered: app.ask("Delete message","delete_message",{id:modelData.rowid}) }
                                    } }
                                }
                                Label { textFormat: Text.PlainText; width: parent.width; wrapMode: Text.Wrap; visible: modelData.metadata.snr !== undefined && modelData.metadata.snr !== null; text: "SNR " + modelData.metadata.snr + " dB · RSSI " + (modelData.metadata.rssi || "—") + " dBm" + (modelData.metadata.hop_start !== undefined ? " · hops " + (modelData.metadata.hop_start-modelData.metadata.hop_limit) : ""); font.pixelSize: 10; color: app.muted }
                            }
                        }
                    }
                    Label { objectName: "emptyChatHint"; textFormat: Text.PlainText; anchors.centerIn: parent; visible: messages.count === 0 && (!app || !app.keyboardOpen); text: app ? app.tr("A little less noise.\nA little more connection.") : "A little less noise.\nA little more connection."; horizontalAlignment: Text.AlignHCenter; color: app ? app.muted : "gray"; font.pixelSize: 20; lineHeight: 1.4 }
                    ScrollBar.vertical: ScrollBar {}
                }
                RowLayout { visible: view.replyId !== "0"; Label { textFormat: Text.PlainText; Layout.fillWidth: true; text: "Replying: " + view.replyText; elide: Text.ElideRight; color: app ? app.accent : "white" } MeshToolButton { text: "×"; onClicked: {replyId="0";replyText="";} } }
                RowLayout {
                    Layout.fillWidth: true; spacing: 10
                    ScrollView {
                        Layout.fillWidth: true; Layout.preferredHeight: Math.min(108,Math.max(58,composer.implicitHeight))
                        TextArea { id: composer; objectName: "composer"; text: app ? app.s.draft : ""; placeholderText: app ? app.tr("Write a message…") : "Write a message…"; wrapMode: TextEdit.Wrap; selectByMouse: true; onTextChanged: if(app && activeFocus)app.act("draft",{text:text}); Keys.onPressed: if(event.key === Qt.Key_Return && (event.modifiers & Qt.ControlModifier)){sendButton.clicked();event.accepted=true;} }
                    }
                    MeshButton { id: sendButton; objectName: "sendMessage"; text: app ? app.tr("Send  ↑") : "Send  ↑"; highlighted: true; Layout.preferredHeight: 48; enabled: app && app.s.connected && !app.s.busy && composer.text.trim().length > 0 && bridge.messageBytes(composer.text) <= 233; onClicked: if(enabled){ app.act("send",{text:composer.text,reply:replyId});replyId="0";replyText=""; } }
                }
                RowLayout {
                    Layout.fillWidth: true
                    Label { textFormat: Text.PlainText; text: app ? app.tr("Ctrl+Enter to send · up to 233 UTF-8 bytes") : "Ctrl+Enter to send · up to 233 UTF-8 bytes"; color: app ? app.muted : "gray"; font.pixelSize: 10; Layout.fillWidth: true; Layout.minimumWidth: 0; wrapMode: Text.Wrap }
                    Label { textFormat: Text.PlainText; objectName: "byteCounter"; text: bridge.messageBytes(composer.text) + "/233"; color: bridge.messageBytes(composer.text) > 233 ? "#ffb796" : app.muted; font.pixelSize: 11 }
                }
            }
        }
    }
}
