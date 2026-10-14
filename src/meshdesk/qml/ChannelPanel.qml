import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15

ScrollView {
    id: view; property var app; property var shareChannels: [0]; implicitWidth: 0; contentWidth: availableWidth; clip: true
    ColumnLayout {
        width: view.availableWidth; spacing: 12
        Label { textFormat: Text.PlainText; text: app ? app.tr("Share your channels") : "Share your channels"; font.pixelSize: 22; font.bold: true }
        Label { textFormat: Text.PlainText; text: app ? app.tr("The link and QR code contain channel keys. Share them with people you want to join your mesh.") : "The link and QR code contain channel keys. Share them with people you want to join your mesh."; Layout.fillWidth: true; wrapMode: Text.Wrap; color: app ? app.muted : "gray" }
        Flow {
            Layout.fillWidth: true; spacing: 8
            Repeater {
                model: app ? app.s.conversations.filter(function(c){return c.peer===0;}) : []
                delegate: CheckBox {
                    text: modelData.name; checked: view.shareChannels.indexOf(modelData.channel)>=0
                    onToggled: {var next=view.shareChannels.slice();var i=next.indexOf(modelData.channel);if(checked && i<0)next.push(modelData.channel);else if(!checked && i>=0)next.splice(i,1);view.shareChannels=next;}
                }
            }
        }
        Flow {
            Layout.fillWidth: true; spacing: 8
            CheckBox { id: addChannels; text: app.tr("Add channels") }
            MeshButton { width: Math.min(implicitWidth,parent.width); text: app.tr("Read channels & create QR"); enabled: app && app.s.connected && !app.s.busy && view.shareChannels.length>0; onClicked: app.act("export_channels",{indices:view.shareChannels,add:addChannels.checked}) }
        }
        Image { visible: app && app.s.qr_url !== ""; source: visible ? "image://qr/" + encodeURIComponent(app.s.qr_url) : ""; sourceSize.width: 260; sourceSize.height: 260; Layout.preferredWidth: 260; Layout.preferredHeight: visible ? 260 : 0; fillMode: Image.PreserveAspectFit; smooth: false; cache: false }
        TextArea { Layout.fillWidth: true; visible: app && app.s.qr_url !== ""; text: app ? app.s.qr_url : ""; readOnly: true; selectByMouse: true; wrapMode: TextEdit.Wrap; font.pixelSize: 12 }
        RowLayout {
            MeshButton { text: app ? app.tr("Copy link") : "Copy link"; enabled: app && app.s.qr_url !== ""; onClicked: app.act("copy",{text:app.s.qr_url}) }
            MeshButton { text: app ? app.tr("Save QR") : "Save QR"; enabled: app && app.s.qr_url !== ""; onClicked: app.act("export",{kind:"qr"}) }
        }
        Label { textFormat: Text.PlainText; text: app ? app.tr("Import a channel link") : "Import a channel link"; font.pixelSize: 22; font.bold: true; topPadding: 16 }
        TextArea { id: channelUrl; Layout.fillWidth: true; placeholderText: app ? app.tr("https://meshtastic.org/e/#…") : "https://meshtastic.org/e/#…"; wrapMode: TextEdit.Wrap; selectByMouse: true }
        MeshButton { text: app ? app.tr("Preview import") : "Preview import"; onClicked: app.act("import_preview",{url:channelUrl.text}) }
        Repeater {
            model: app ? app.s.import_preview : []
            delegate: RowLayout {
                Layout.fillWidth: true
                Label { textFormat: Text.PlainText; text: modelData.name || app.tr("Primary"); Layout.fillWidth: true; Layout.minimumWidth: 0; elide: Text.ElideRight }
                MeshComboBox {
                    model: ["Skip","Channel 0 · Primary","Channel 1","Channel 2","Channel 3","Channel 4","Channel 5","Channel 6","Channel 7"]
                    currentIndex: modelData.target+1
                    onActivated: app.act("import_target",{index:modelData.index,target:currentIndex-1})
                }
            }
        }
        CheckBox { visible: app && app.s.import_preview.length>0; text: app.tr("Update LoRa configuration"); checked: app && app.s.import_lora; onToggled: app.act("import_lora",{value:checked}) }
        CheckBox { id: replaceAll; visible: app && app.s.import_preview.length>0; text: app.tr("Disable channels not included in this import") }
        MeshButton { text: app.tr("Apply channel import"); highlighted: true; visible: app && app.s.import_preview.length>0; enabled: app && app.s.connected && !app.s.busy; onClicked: app.ask("Apply the selected channel mappings to the radio","import_apply",{replace:replaceAll.checked}) }
    }
}
