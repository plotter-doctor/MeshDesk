import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15

Item {
    id: view
    property var app
    property bool advanced: false
    property string displayedSection: app ? app.s.settings_section : ""
    onDisplayedSectionChanged: {
        if (fieldScroll && fieldScroll.contentItem) fieldScroll.contentItem.contentY=0;
        if (sections && app) sections.positionViewAtIndex(app.s.sections.findIndex(function(s){return s.key===displayedSection;}),ListView.Contain);
    }
    function loadSection(key) {
        app.act("setting_load",{section:key});
    }
    ColumnLayout {
        anchors.fill: parent; anchors.margins: 18; spacing: 10
        RowLayout {
            Label { textFormat: Text.PlainText; text: app ? app.tr("Radio settings") : "Radio settings"; font.pixelSize: 25; font.bold: true; Layout.fillWidth: true }
            Label { textFormat: Text.PlainText; text: app && app.s.settings_dirty ? "Unsaved changes" : ""; color: app ? app.accent : "white" }
            BusyIndicator { running: app && app.s.settings_loading; visible: running; implicitWidth: 30; implicitHeight: 30 }
        }
        TabBar {
            id: tabs; currentIndex: app ? app.settingsTab : 0; onCurrentIndexChanged: if(app)app.settingsTab=currentIndex; objectName: "settingsTabs"; Layout.fillWidth: true
            TabButton { text: app ? app.tr(app.compact ? "Config" : "Configuration") : "Configuration" }
            TabButton { text: app ? app.tr(app.compact ? "Channels" : "Channels & QR") : "Channels & QR" }
            TabButton { text: app ? app.tr(app.compact ? "Actions" : "Radio actions") : "Radio actions" }
        }
        StackLayout {
            currentIndex: tabs.currentIndex; Layout.fillWidth: true; Layout.fillHeight: true
            RowLayout {
                spacing: 14
                ListView {
                    id: sections; visible: !app || !app.compact; objectName: "settingsSections"; Layout.preferredWidth: app && app.compact ? 140 : 200; Layout.fillHeight: true; clip: true
                    model: app ? app.s.sections : []
                    section.property: "group"; section.delegate: Label { textFormat: Text.PlainText; text: section; font.bold: true; color: app ? app.accent : "white"; topPadding: 18; bottomPadding: 8; font.pixelSize: 12 }
                    delegate: ItemDelegate {
                        width: sections.width; height: 43; text: (app && app.s.pending_settings.indexOf(modelData.key)>=0 ? "● " : "") + (app ? app.tr(modelData.title) : modelData.title); highlighted: app && app.s.settings_section === modelData.key
                        enabled: app && app.s.connected && !app.s.settings_loading
                        onClicked: view.loadSection(modelData.key)
                    }
                    ScrollBar.vertical: ScrollBar {}
                }
                ColumnLayout {
                    Layout.fillWidth: true; Layout.fillHeight: true
                    MeshComboBox {
                        objectName: "compactSettingsSection"; visible: app && app.compact; Layout.fillWidth: true
                        model: app ? app.s.sections : []; textRole: "title"
                        enabled: app && app.s.connected && !app.s.settings_loading
                        currentIndex: app ? app.s.sections.findIndex(function(s){return s.key===app.s.settings_section;}) : 0
                        onActivated: view.loadSection(app.s.sections[currentIndex].key)
                    }
                    RowLayout {
                        Label { textFormat: Text.PlainText; text: app ? app.s.settings_section : ""; font.bold: true; Layout.fillWidth: true; elide: Text.ElideRight }
                        Switch { text: app.tr("JSON"); checked: view.advanced; onToggled: view.advanced=checked }
                        MeshToolButton { text: "↻"; enabled: app && app.s.connected && !app.s.settings_loading; onClicked: app.ask("Reload this section and discard its draft", "setting_load",{section:app.s.settings_section,discard:true}) }
                    }
                    Label { textFormat: Text.PlainText; Layout.fillWidth: true; visible: text !== ""; text: app ? app.s.settings_error : ""; color: "#ffb796"; wrapMode: Text.Wrap }
                    Label { textFormat: Text.PlainText; Layout.fillWidth: true; visible: app && !app.s.fields.length && !app.s.settings_loading; text: app ? app.tr("Choose a section to read its current values from the radio.") : "Choose a section to read its current values from the radio."; color: app ? app.muted : "gray"; wrapMode: Text.Wrap }
                    ScrollView {
                        id: fieldScroll; objectName: "settingsFieldScroll"
                        Layout.fillWidth: true; Layout.fillHeight: true; clip: true; contentWidth: availableWidth; visible: !view.advanced
                        ColumnLayout {
                            width: parent.width; spacing: 12
                            Repeater {
                                model: bridge.fieldsModel
                                delegate: ColumnLayout {
                                    id: fieldRow; Layout.fillWidth: true
                                    property var field: fieldData
                                    Label { textFormat: Text.PlainText; text: fieldRow.field.group || ""; visible: text.length > 0; font.pixelSize: 20; font.bold: true; color: app.accent; topPadding: 12; Layout.fillWidth: true; wrapMode: Text.Wrap }
                                    Label { textFormat: Text.PlainText; text: fieldRow.field.title; font.bold: true; Layout.fillWidth: true; wrapMode: Text.Wrap }
                                    Label { textFormat: Text.PlainText; text: fieldRow.field.description || ""; visible: text !== ""; Layout.fillWidth: true; wrapMode: Text.Wrap; color: app ? app.muted : "gray"; font.pixelSize: 11 }
                                    Label { textFormat: Text.PlainText; text: fieldRow.field.path; font.pixelSize: 10; color: app ? app.muted : "gray"; visible: fieldRow.field.path.indexOf(".") >= 0 }
                                    Loader {
                                        Layout.fillWidth: true
                                        sourceComponent: fieldRow.field.kind === "bool" ? boolEditor : fieldRow.field.kind === "enum" ? enumEditor : fieldRow.field.kind === "bitmask" ? bitmaskEditor : stringEditor
                                        Component {
                                            id: bitmaskEditor
                                            Flow {
                                                spacing: 6
                                                Repeater {
                                                    model: fieldRow.field.choices
                                                    CheckBox {
                                                        id: flagControl
                                                        width: Math.min(implicitWidth,parent.width)
                                                        enabled: !fieldRow.field.disabled && !app.s.settings_loading
                                                        text: modelData.label; checked: (Number(fieldRow.field.value) & modelData.value) !== 0
                                                        contentItem: Label {
                                                            textFormat: Text.PlainText; text: flagControl.text; font: flagControl.font; color: app.ink
                                                            leftPadding: flagControl.indicator.width+flagControl.spacing
                                                            verticalAlignment: Text.AlignVCenter; wrapMode: Text.Wrap
                                                            opacity: flagControl.enabled ? 1 : 0.5
                                                        }
                                                        onToggled: app.act("setting_edit",{path:fieldRow.field.path,value:checked ? Number(fieldRow.field.value) | modelData.value : Number(fieldRow.field.value) & ~modelData.value})
                                                    }
                                                }
                                            }
                                        }
                                        Component {
                                            id: boolEditor
                                            Switch { checked: fieldRow.field.value; onToggled: app.act("setting_edit",{path:fieldRow.field.path,value:checked}); text: checked ? "Enabled" : "Disabled"; enabled: !fieldRow.field.disabled && !app.s.settings_loading }
                                        }
                                        Component {
                                            id: enumEditor
                                            MeshComboBox {
                                                model: fieldRow.field.choices; textRole: "label"; enabled: !fieldRow.field.disabled && !app.s.settings_loading
                                                currentIndex: { for(var i=0;i<fieldRow.field.choices.length;i++)if(fieldRow.field.choices[i].value===fieldRow.field.value)return i;return -1; }
                                                onActivated: app.act("setting_edit",{path:fieldRow.field.path,value:fieldRow.field.choices[currentIndex].value})
                                            }
                                        }
                                        Component {
                                            id: stringEditor
                                            RowLayout {
                                                TextField {
                                                    id: valueField; objectName: "field_" + fieldRow.field.path; Layout.fillWidth: true
                                                    text: String(fieldRow.field.value); selectByMouse: true; enabled: !app.s.settings_loading
                                                    readOnly: fieldRow.field.disabled
                                                    echoMode: fieldRow.field.secret && !showSecret.checked ? TextInput.Password : TextInput.Normal
                                                    onEditingFinished: if(text !== String(fieldRow.field.value))app.act("setting_edit",{path:fieldRow.field.path,value:text})
                                                    placeholderText: fieldRow.field.kind === "bytes" ? "Base64 encoded bytes" : fieldRow.field.kind === "json" ? "JSON array" : ""
                                                }
                                                MeshToolButton { id: showSecret; visible: fieldRow.field.secret; checkable: true; text: checked ? "Hide" : "Show" }
                                                MeshToolButton { text: app.tr("Copy"); visible: fieldRow.field.kind === "bytes"; onClicked: app.act("copy",{text:String(fieldRow.field.value)}) }
                                            }
                                        }
                                    }
                                }
                            }
                        }
                    }
                    ScrollView {
                        implicitWidth: 0; contentWidth: availableWidth
                        Layout.fillWidth: true; Layout.fillHeight: true; visible: view.advanced; clip: true
                        TextArea { id: jsonEditor; text: app ? app.s.settings_json : "{}"; wrapMode: TextEdit.Wrap; selectByMouse: true; font.family: "monospace"; font.pixelSize: 12 }
                    }
                    Flow {
                        Layout.fillWidth: true; spacing: 4
                        MeshButton { text: app.tr("Save all")+" ("+app.s.pending_settings.length+")"; visible: app.s.pending_settings.length>1; enabled: !app.s.settings_loading && !view.advanced; highlighted: true; onClicked: {forceActiveFocus();app.ask("Save all staged settings to the radio","setting_save_all");} }
                        MeshButton { text: app.tr("Discard all"); visible: app.s.pending_settings.length>1; enabled: !app.s.settings_loading; onClicked: app.ask("Discard all staged settings","setting_discard_all") }
                        MeshButton { text: app ? app.tr("Apply JSON to draft") : "Apply JSON to draft"; visible: view.advanced; onClicked: {app.act("setting_json",{text:jsonEditor.text});view.advanced=false;} }
                        MeshButton { objectName: "saveSettings"; text: app ? app.tr("Save to radio") : "Save to radio"; highlighted: true; enabled: app && app.s.connected && app.s.fields.length > 0 && !app.s.settings_loading && !view.advanced; onClicked: {forceActiveFocus();app.ask("Save settings to the radio", "setting_save");} }
                        MeshButton { text: app ? app.tr("Discard") : "Discard"; enabled: app && app.s.settings_dirty; onClicked: app.act("setting_discard") }
                        MeshButton { text: app ? app.tr("Export") : "Export"; onClicked: app.act("export",{kind:"settings"}) }
                        MeshButton { text: app ? app.tr("Import") : "Import"; onClicked: app.act("import_settings_file") }
                        MeshButton { text: app ? app.tr("New channel key") : "New channel key"; visible: app && app.s.settings_section.indexOf("channel.") === 0; onClicked: keyMenu.open(); Menu { id: keyMenu; Repeater { model: [256,128,8,0]; delegate: MenuItem { text: modelData+" bit"; onTriggered: app.act("generate_channel_key",{bits:modelData}) } } } }
                        MeshButton { text: app ? app.tr("New identity") : "New identity"; visible: app && app.s.settings_section === "config.security"; onClicked: app.ask("Stage a new identity key pair","generate_identity") }
                        MeshButton { text: app ? app.tr("Back up identity") : "Back up identity"; visible: app && app.s.settings_section === "config.security"; onClicked: app.act("export",{kind:"identity"}) }
                        MeshButton { text: app ? app.tr("Print identity") : "Print identity"; visible: app && app.s.settings_section === "config.security"; onClicked: app.act("print_identity") }
                    }
                }
            }
            ChannelPanel { app: view.app }
            RadioActions { app: view.app }
        }
    }
}
