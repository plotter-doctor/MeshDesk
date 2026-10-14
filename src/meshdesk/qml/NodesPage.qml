import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15

Item {
    id: view
    property var app
    property var selected: app ? app.s.selected_node : ({})
    property bool rawDetails: false
    property real selectedNumber: selected.num || 0
    onSelectedNumberChanged: if (nodeDetails && nodeDetails.contentItem) nodeDetails.contentItem.contentY=0
    NodeFilters { id: filters; app: view.app }
    function command(name, args) { app.act("command", {name:name,args:args || {node:selected.num}}); }
    RowLayout {
        anchors.fill: parent; anchors.margins: 18; spacing: 16
        ColumnLayout {
            visible: !app || !app.compact || !selected.num
            Layout.preferredWidth: 270; Layout.maximumWidth: app && app.compact ? Infinity : 270; Layout.fillWidth: app && app.compact; Layout.fillHeight: true
            Label { textFormat: Text.PlainText; text: app ? app.tr("Your mesh") : "Your mesh"; font.pixelSize: 25; font.bold: true }
            TextField { id: search; Layout.fillWidth: true; placeholderText: app ? app.tr("Find a node…") : "Find a node…" }
            RowLayout {
                CheckBox { id: favorites; text: app ? app.tr("Favorites") : "Favorites" }
                MeshButton { text: app.tr("Filters"); onClicked: filters.open() }
            }
            RowLayout {
                Layout.fillWidth: true
                MeshComboBox {
                    Layout.fillWidth: true
                    model: [app.tr("Name"),app.tr("Hops"),app.tr("Last heard"),"SNR",app.tr("Hardware"),"MAC"]
                    currentIndex: ["name","hops","heard","snr","hardware","mac"].indexOf(app.s.node_sort)
                    onActivated: app.act("preference",{key:"node_sort",value:["name","hops","heard","snr","hardware","mac"][currentIndex]})
                }
                MeshToolButton { text: app.s.node_sort_desc ? "↓" : "↑"; onClicked: app.act("preference",{key:"node_sort_desc",value:!app.s.node_sort_desc}) }
            }
            ListView {
                id: nodeList; objectName: "nodeList"; Layout.fillWidth: true; Layout.fillHeight: true; clip: true; spacing: 4
                model: app ? app.s.filtered_nodes : []
                delegate: ItemDelegate {
                    width: nodeList.width; height: visible ? 68 : 0
                    visible: (!favorites.checked || modelData.favorite) && (modelData.name.toLowerCase().indexOf(search.text.toLowerCase()) >= 0 || String(modelData.num).indexOf(search.text) >= 0 || Number(modelData.num).toString(16).indexOf(search.text.toLowerCase().replace("!","")) >= 0 || modelData.short.toLowerCase().indexOf(search.text.toLowerCase()) >= 0)
                    highlighted: selected.num === modelData.num
                    onClicked: app.act("node",{num:modelData.num})
                    contentItem: ColumnLayout {
                        Label { textFormat: Text.PlainText; Layout.fillWidth: true; text: (modelData.favorite ? "★  " : "") + modelData.name; elide: Text.ElideRight; font.bold: true }
                        Label { textFormat: Text.PlainText; text: "!" + Number(modelData.num).toString(16) + (modelData.ignored ? " · ignored" : ""); font.pixelSize: 11; color: app.muted }
                    }
                }
                ScrollBar.vertical: ScrollBar {}
            }
            MeshButton { text: app ? app.tr("Export nodes") : "Export nodes"; Layout.fillWidth: true; onClicked: app.act("export",{kind:"nodes"}) }
        }
        Rectangle {
            visible: !app || !app.compact || !!selected.num
            Layout.fillWidth: true; Layout.minimumWidth: 0; Layout.fillHeight: true; color: app ? app.panel : "#172733"; radius: 12
            Label { textFormat: Text.PlainText; anchors.centerIn: parent; width: parent.width-32; wrapMode: Text.Wrap; horizontalAlignment: Text.AlignHCenter; visible: !selected.num; text: app ? app.tr("Choose a node to explore") : "Choose a node to explore"; color: app ? app.muted : "gray" }
            ScrollView {
                id: nodeDetails
                anchors.fill: parent; anchors.margins: 20; visible: !!selected.num; clip: true; contentWidth: availableWidth
                ColumnLayout {
                    width: parent.width; spacing: 12
                    MeshButton { text: "‹ " + app.tr("Nodes"); visible: app && app.compact; onClicked: app.act("node",{num:0}) }
                    Label { textFormat: Text.PlainText; text: selected.name || ""; font.pixelSize: 26; font.bold: true; wrapMode: Text.Wrap; Layout.fillWidth: true }
                    Label { textFormat: Text.PlainText; text: selected.num ? "!" + Number(selected.num).toString(16) + (app.s.my_num === selected.num ? " · Your radio" : "") : ""; color: app ? app.accent : "white" }
                    Label { textFormat: Text.PlainText; text: selected.lastHeard ? "Last heard " + new Date(selected.lastHeard*1000).toLocaleString() : "Last heard unavailable"; color: app ? app.muted : "gray"; wrapMode: Text.Wrap; Layout.fillWidth: true }
                    Flow {
                        Layout.fillWidth: true; spacing: 6
                        MeshButton { text: app ? app.tr("Message") : "Message"; enabled: app && selected.num !== app.s.my_num; onClicked: {app.act("chat",{peer:selected.num});app.go("Chat");} }
                        MeshButton { text: selected.favorite ? "★ Unfavorite" : "☆ Favorite"; enabled: app && app.s.connected; onClicked: command(selected.favorite ? "unfavorite" : "favorite",{value:selected.num}) }
                        MeshButton { text: app ? app.tr("Show on map") : "Show on map"; onClicked: {app.act("node",{num:selected.num});app.go("Map");} }
                    }
                    Flow {
                        Layout.fillWidth: true; spacing: 6; enabled: app && app.s.connected
                        MeshButton { text: app ? app.tr("Request position") : "Request position"; onClicked: command("position") }
                        MeshButton { text: app ? app.tr("Traceroute") : "Traceroute"; onClicked: command("traceroute") }
                        MeshButton { text: app ? app.tr("Telemetry") : "Telemetry"; onClicked: command("telemetry") }
                        MeshButton { text: app ? app.tr("Verify identity") : "Verify identity"; onClicked: {command("verify_key",{node:selected.num,type:0});app.go("Activity");} }
                    }
                    Label { textFormat: Text.PlainText; text: app ? app.tr("Node information") : "Node information"; font.bold: true; font.pixelSize: 18 }
                    Repeater {
                        model: app ? app.s.node_details : []
                        delegate: ColumnLayout {
                            Layout.fillWidth: true; spacing: 2
                            Label { textFormat: Text.PlainText; text: modelData.name; color: app ? app.muted : "gray"; font.pixelSize: 11 }
                            Label { textFormat: Text.PlainText; text: modelData.value; Layout.fillWidth: true; wrapMode: Text.WrapAnywhere }
                        }
                    }
                    Switch { text: app.tr("Show raw node data"); checked: view.rawDetails; onToggled: view.rawDetails=checked }
                    TextArea { visible: view.rawDetails; Layout.fillWidth: true; text: app ? app.json(selected) : ""; readOnly: true; selectByMouse: true; wrapMode: TextEdit.Wrap; font.family: "monospace"; font.pixelSize: 12 }
                    Flow {
                        Layout.fillWidth: true; spacing: 6; enabled: app && app.s.connected
                        MeshButton { text: selected.ignored ? "Unignore" : "Ignore"; onClicked: app.ask(text + " node","command",{name:selected.ignored ? "unignore" : "ignore",args:{value:selected.num}}) }
                        MeshButton { text: app ? app.tr("Remove / refresh identity") : "Remove / refresh identity"; enabled: selected.num !== (app ? app.s.my_num : 0); onClicked: app.ask("Remove this node from the radio database","command",{name:"remove_node",args:{value:selected.num}}) }
                    }
                }
            }
        }
    }
}
