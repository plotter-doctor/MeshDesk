import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Controls.Material 2.15
import QtQuick.Layouts 1.15
import QtQuick.Window 2.15

ApplicationWindow {
    id: root
    objectName: "mainWindow"
    // Window dimensions exclude the title bar/borders. Leave room for them
    // when restored; on small displays let the window manager fit its work area.
    Component.onCompleted: {
        if (Screen.desktopAvailableWidth < 1056 || Screen.desktopAvailableHeight < 664)
            showMaximized();
        else
            show();
    }
    width: Math.min(1024, Math.max(1, Screen.desktopAvailableWidth - 32))
    height: Math.min(600, Math.max(1, Screen.desktopAvailableHeight - 64))
    minimumWidth: Math.min(480, Math.max(1, Screen.desktopAvailableWidth - 32))
    minimumHeight: Math.min(440, Math.max(1, Screen.desktopAvailableHeight - 64))
    title: "MeshDesk"
    property var s: JSON.parse(bridge.stateJson)
    property string page: "Chat"
    onPageChanged: act("page",{name:page})
    property color bg: s.theme === "light" ? "#edf2f3" : "#101b24"
    property color panel: s.theme === "light" ? "#ffffff" : "#172733"
    property color ink: s.theme === "light" ? "#152731" : "#e6f1f4"
    property color muted: s.theme === "light" ? "#56707d" : "#94aebd"
    property color accent: s.theme === "light" ? "#16664e" : "#62dcb0"
    property bool compact: width < 760
    property bool compactHeader: width < 960
    property bool keyboardOpen: touchKeyboard.height > 0
    property int settingsTab: 0
    property string pendingAction: ""
    property var pendingArgs: ({})
    property string toastText: ""
    Material.theme: s.theme === "light" ? Material.Light : Material.Dark
    Material.accent: accent
    Material.primary: panel
    Material.background: bg
    font: bridge.interfaceFont
    color: bg

    function act(action, args) { bridge.dispatch(action, JSON.stringify(args || {})); }
    function ask(title, action, args) {
        confirmDialog.title = root.tr(title); pendingAction = action; pendingArgs = args || {}; confirmDialog.open();
    }
    function go(name) { page = name; }
    function json(value) { return JSON.stringify(value, null, 2); }
    function tr(text) { return bridge.translate(text,s.language); }

    Connections {
        target: bridge
        function onToast(text) { root.toastText = text; toastTimer.restart(); }
        function onNavigate(name) { root.page = name; }
    }
    Shortcut { sequence: "Ctrl+K"; onActivated: commandDialog.open() }
    Shortcut { sequence: "Ctrl+1"; onActivated: root.page = "Chat" }
    Shortcut { sequence: "Ctrl+2"; onActivated: root.page = "Nodes" }
    Shortcut { sequence: "Ctrl+3"; onActivated: root.page = "Map" }
    Shortcut { sequence: "Ctrl+4"; onActivated: root.page = "Settings" }

    header: Rectangle {
        height: 68; color: root.panel
        RowLayout {
            anchors.fill: parent; anchors.leftMargin: root.compactHeader ? 12 : 22; anchors.rightMargin: root.compactHeader ? 12 : 18; spacing: root.compactHeader ? 8 : 16
            Rectangle {
                width: 36; height: 36; radius: 10; color: root.accent
                Label { textFormat: Text.PlainText; anchors.centerIn: parent; text: root.tr("M"); color: root.s.theme === "light" ? "#ffffff" : "#10232a"; font.bold: true; font.pixelSize: 23 }
            }
            ColumnLayout {
                visible: !root.compactHeader
                spacing: 1
                Label { textFormat: Text.PlainText; text: "MeshDesk"; color: root.ink; font.bold: true; font.pixelSize: 20 }
                Label { textFormat: Text.PlainText; text: root.s.active === "simulator" ? "LOCAL SIMULATOR" : "YOUR MESH, CLOSE AT HAND"; color: root.muted; font.pixelSize: 9; font.letterSpacing: 1.4 }
            }
            Item { Layout.fillWidth: true }
            Rectangle { width: 8; height: 8; radius: 4; color: root.s.connected ? root.accent : "#e6ad65" }
            Label { textFormat: Text.PlainText; text: root.tr(root.s.busy ? "Working…" : (root.s.status || "Offline")); color: root.s.busy ? root.accent : root.muted; visible: !root.compactHeader }
            MeshToolButton { text: "⚿"; visible: root.s.backup_due; ToolTip.text: root.tr("Back up identity"); ToolTip.visible: hovered; onClicked: backupDialog.open() }
            MeshToolButton { text: "●"; visible: Object.keys(root.s.notification || {}).length > 0; onClicked: root.go("Activity"); ToolTip.text: root.tr("Radio notification"); ToolTip.visible: hovered }
            MeshButton { text: root ? root.tr("⌘  Commands") : "⌘  Commands"; onClicked: commandDialog.open(); visible: !root.compactHeader }
            MeshToolButton { text: "⌨"; visible: bridge.keyboardAvailable; focusPolicy: Qt.NoFocus; onClicked: Qt.inputMethod.visible ? Qt.inputMethod.hide() : Qt.inputMethod.show() }
            MeshToolButton { text: "⋯"; onClicked: commandDialog.open(); visible: root.compactHeader }
            MeshButton {
                objectName: "exitButton"; text: root.tr("Exit")
                ToolTip.text: root.tr("Exit MeshDesk"); ToolTip.visible: hovered
                onClicked: root.close()
            }
        }
    }

    RowLayout {
        anchors.fill: parent; anchors.bottomMargin: touchKeyboard.height; spacing: 0
        Rectangle {
            Layout.fillHeight: true; Layout.preferredWidth: root.compact ? 62 : 92; color: root.panel
            ScrollView {
                anchors.fill: parent; anchors.margins: 7; clip: true
                contentWidth: availableWidth
                ColumnLayout {
                width: parent.width; spacing: 5
                Repeater {
                    model: [{name:"Chat",symbol:"◌"},{name:"Nodes",symbol:"◈"},{name:"Map",symbol:"⌖"},{name:"Settings",symbol:"⚙"},{name:"Connections",symbol:"⇄"},{name:"Activity",symbol:"≋"},{name:"Preferences",symbol:"☰"}]
                    delegate: ItemDelegate {
                        Layout.fillWidth: true; Layout.preferredHeight: 59
                        objectName: "nav" + modelData.name
                        highlighted: root.page === modelData.name
                        onClicked: root.page = modelData.name
                        background: Rectangle { color: root.page === modelData.name ? (root.s.theme === "light" ? "#d4e9e3" : "#24413f") : "transparent"; radius: 9 }
                        contentItem: Column {
                            spacing: 3
                            Label { textFormat: Text.PlainText; anchors.horizontalCenter: parent.horizontalCenter; text: modelData.symbol; color: root.page === modelData.name ? root.accent : root.muted; font.pixelSize: 23 }
                            Label { textFormat: Text.PlainText; anchors.horizontalCenter: parent.horizontalCenter; text: root.tr(modelData.name); color: root.page === modelData.name ? root.accent : root.muted; font.pixelSize: root.compact ? 8 : 10 }
                        }
                    }
                }
                }
            }
        }
        Loader {
            id: pageLoader
            objectName: "pageLoader"
            Layout.fillWidth: true; Layout.fillHeight: true
            Component.onCompleted: setSource(root.page + "Page.qml", {app:root})
            Connections { target: root; function onPageChanged() { pageLoader.setSource(root.page + "Page.qml", {app:root}); } }
        }
    }

    Loader {
        id: touchKeyboard; objectName: "touchKeyboardLoader"; anchors.left: parent.left; anchors.right: parent.right; anchors.bottom: parent.bottom
        z: 90; active: bridge.keyboardAvailable; source: active ? "TouchKeyboard.qml" : ""
        height: item && item.active ? item.implicitHeight : 0
    }

    Rectangle {
        anchors.horizontalCenter: parent.horizontalCenter; anchors.bottom: parent.bottom; anchors.bottomMargin: 16
        width: Math.min(root.width - 60, 720); height: toastLabel.implicitHeight + 28; radius: 9
        color: "#365447"; visible: root.toastText !== ""; z: 100
        Label { textFormat: Text.PlainText; id: toastLabel; anchors.fill: parent; anchors.margins: 14; text: root.toastText; wrapMode: Text.Wrap; color: "#ffffff" }
        MouseArea { anchors.fill: parent; onClicked: root.toastText = "" }
    }
    Timer { id: toastTimer; interval: 8500; onTriggered: root.toastText = "" }

    MeshDialog {
        id: backupDialog; objectName: "backupDialog"; title: root.tr("Back up identity"); modal: true; anchors.centerIn: parent
        width: Math.min(root.width-40,460)
        ColumnLayout {
            width: parent.width
            Label { textFormat: Text.PlainText; text: bridge.translateKey("dialog.pkiBackupReminder.description",root.s.language); Layout.fillWidth: true; wrapMode: Text.Wrap }
            MeshButton { text: root.tr("Back up now"); onClicked: {root.settingsTab=0;root.act("backup_reminder",{days:1,open:true});backupDialog.close();} }
            MeshButton { text: bridge.translateKey("dialog.pkiBackupReminder.remindLaterPrefix",root.s.language)+" 7 "+bridge.translateKey("common.unit.day.plural",root.s.language); onClicked: {root.act("backup_reminder",{days:7});backupDialog.close();} }
            MeshButton { text: root.tr("Never remind me"); onClicked: {root.act("backup_reminder",{days:36500});backupDialog.close();} }
        }
    }

    MeshDialog {
        id: confirmDialog; objectName: "confirmDialog"; modal: true; anchors.centerIn: parent; width: Math.min(root.width - 40, 510)
        standardButtons: Dialog.Ok | Dialog.Cancel
        Label { textFormat: Text.PlainText; width: parent.width; text: root ? root.tr("Apply this action to the selected radio or conversation?") : "Apply this action to the selected radio or conversation?"; wrapMode: Text.Wrap }
        onAccepted: root.act(root.pendingAction, root.pendingArgs)
    }

    MeshDialog {
        id: commandDialog; objectName: "commandDialog"; title: root ? root.tr("Commands") : "Commands"; modal: true; anchors.centerIn: parent
        width: Math.min(root.width - 40, 620); height: Math.min(root.height - 50, 520)
        ColumnLayout {
            anchors.fill: parent
            TextField { id: commandSearch; Layout.fillWidth: true; placeholderText: root ? root.tr("Find an action…") : "Find an action…"; focus: true }
            CheckBox { id: pinnedOnly; text: root.tr("Pinned groups") }
            ListView {
                id: commandList; objectName: "commandList"
                Layout.fillWidth: true; Layout.fillHeight: true; clip: true
                model: root.s.commands.filter(function(c) {
                    return c.title.toLowerCase().indexOf(commandSearch.text.toLowerCase()) >= 0 &&
                           (!pinnedOnly.checked || root.s.pinned_command_groups.indexOf(c.group)>=0);
                })
                section.property: "group"
                section.delegate: RowLayout {
                    width: commandList.width; height: 42
                    Label { textFormat: Text.PlainText; text: {var c=root.s.commands.find(function(c){return c.group===section;});return c ? c.group_label : section;} color: root.accent; font.bold: true; Layout.fillWidth: true }
                    MeshToolButton {
                        text: root.s.pinned_command_groups.indexOf(section)>=0 ? "★" : "☆"
                        onClicked: {var pins=root.s.pinned_command_groups.slice();var i=pins.indexOf(section);if(i>=0)pins.splice(i,1);else pins.push(section);root.act("preference",{key:"pinned_command_groups",value:pins});}
                    }
                }
                delegate: ItemDelegate {
                    width: ListView.view.width; height: 48
                    text: modelData.title
                    onClicked: {
                        commandDialog.close();
                        if (modelData.page) {root.settingsTab=modelData.tab || 0;root.go(modelData.page);}
                        else if (modelData.command) root.ask(modelData.title, "command", {name:modelData.command,args:{value:1}});
                        else if (modelData.confirm) root.ask(modelData.title, modelData.action, modelData.args || {});
                        else root.act(modelData.action, modelData.args || {});
                    }
                }
                ScrollBar.vertical: ScrollBar {}
            }
        }
    }
}
